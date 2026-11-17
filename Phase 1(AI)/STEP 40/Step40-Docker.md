# Step 40: Docker

> **Covers:** packaging an AI application as an immutable image — Dockerfile instructions and what each one actually commits to, image vs. container and the build/run lifecycle, layer caching that makes rebuilds fast (or miserably slow), volumes for data that must outlive a container (Qdrant, SQLite checkpoints, reports, model caches), container networking and service discovery, multi-stage builds that keep compilers and `node_modules` out of production, image hygiene and non-root containers, Docker Compose for the whole stack, and registries/tags for shipping the exact artifact you tested. Verified against Docker's documentation in October 2026.

---

## The Problem

"Works on my machine" is not a joke in AI engineering; it is a deployment plan that fails on contact. WhyTheDiff needs Python 3.14, a specific lockfile, FastEmbed model downloads, an embedded Qdrant directory, SQLite checkpoints, saved reports, and a built React bundle. Install those by hand on a server and you have reproduced your laptop — including the parts you forgot you changed.

Docker replaces that list with one artifact: an **image** containing the runtime, the dependencies, and the code, built once and run identically on your machine, a teammate's, CI, and the deploy target. For Step 41, the platform will not install Python for you; it will run a container. This step is the difference between "deployable" and "deployed."

---

## Foundational Concepts

### Docker is not a virtual machine

A VM virtualizes hardware and runs a full guest OS. A container is an ordinary process on the host, isolated with Linux **namespaces** (what it can see: filesystem, network, process IDs) and constrained with **cgroups** (what it can use: CPU, memory). It shares the host kernel, so it starts in milliseconds and has almost no idle overhead. The trade-off: a container is only as isolated as its configuration — which is why 40.7 is not optional.

### The vocabulary that actually matters

| Term | What it is | Mental model |
|---|---|---|
| **Dockerfile** | a text recipe of build instructions | the source code of the image |
| **Image** | an immutable, layered filesystem plus config (env, user, entrypoint) | the compiled artifact |
| **Container** | a running process using an image plus a thin writable layer | the process, not the artifact |
| **Registry** | a store for images, addressed by repository and tag | npm/PyPI for containers |
| **Volume** | Docker-managed storage outside the container's lifecycle | the only thing that survives |
| **Build context** | the directory sent to the builder | what `COPY` can see |
| **Layer** | one cached filesystem diff produced by a Dockerfile instruction | the unit of caching |

### What happens on `docker build` and `docker run`

```text
Dockerfile + build context
        │  docker build
        ▼
   image (layers + config)  ──docker push──▶  registry
        │  docker run                              │
        ▼                                          │ docker pull
   container = process + writable layer  ◀─────────┘
        │
        └── deleted → writable layer gone; volumes remain
```

Two consequences drive every practice in this step. First, **the image must contain everything the process needs at runtime**, because the server will not have your shell, your virtualenv, or your `.env`. Second, **the container must contain nothing it does not need**, because everything you add is attack surface, pull time, and disk.

### Why AI projects feel this more than CRUD apps

- **Dependency matrices are brutal.** Python, CUDA, cuDNN, compiler versions, and wheels that only exist for certain platforms. Containers pin the userspace side; the host provides only the kernel and (for GPUs) the driver.
- **Artifacts are large.** Model weights and embedding caches are hundreds of megabytes to tens of gigabytes; they belong in volumes, not in images or rebuild loops.
- **Stacks are multi-service.** An API, a vector database, a frontend, maybe a worker. Compose exists for exactly this shape.
- **Evaluation must be reproducible.** The same image that served a report should be the one that produced the eval numbers.

### The map of this step

| Layer | What you decide | Section |
|---|---|---|
| **The recipe** | base image, instructions, what gets copied | 40.1 |
| **The lifecycle** | build once, run many, dispose safely | 40.2 |
| **The cache** | which rebuilds are seconds and which are minutes | 40.3 |
| **The state** | what survives a container (and a `down -v`) | 40.4 |
| **The wires** | how containers find and expose each other | 40.5 |
| **The artifact** | build tools out, runtime only in | 40.6 |
| **The hardening** | non-root, pinned, scanned, no secrets | 40.7 |
| **The topology** | one command for API + frontend + Qdrant | 40.8 |
| **The shipment** | tags, digests, registry, GPU notes | 40.9 |

---

## 40.1 Dockerfile Instructions

**Motivate.** A Dockerfile is executable infrastructure. A misplaced `COPY . .` can bake your `.env` into an image layer forever; a missing `USER` means the process runs as root; a `CMD` in shell form means your server never receives `SIGTERM` and gets killed ten seconds later.

**Define.** Each instruction changes the image's filesystem or metadata. The core set:

| Instruction | What it does | Gotcha |
|---|---|---|
| `FROM` | starts a stage from a base image | tags are mutable; pin a digest for reproducibility |
| `WORKDIR` | sets the working directory for later instructions | use absolute paths |
| `COPY` | copies from the build context or another stage | cannot see outside the context; prefer it over `ADD` |
| `ADD` | like `COPY`, plus remote URLs and tar extraction | surprising behavior; use only when those features are needed |
| `RUN` | executes a command **at build time** | each `RUN` is a layer; chain related commands |
| `ENV` | sets an environment variable **in the image** | visible in `docker inspect`; never put secrets here |
| `ARG` | build-time variable | also recoverable from image history; not a secret store |
| `EXPOSE` | documents the listening port | does not publish it; `-p` does |
| `USER` | switches the runtime user | do this before `CMD`; create the user first |
| `CMD` | default command for the container | exec form (`["uvicorn", ...]`) so signals reach the process |
| `ENTRYPOINT` | fixed executable; `CMD` becomes its default arguments | useful for wrappers; don't overuse |
| `HEALTHCHECK` | command Docker runs to test liveness | make it hit a real endpoint |

**Show.** A first, deliberately single-stage Dockerfile for WhyTheDiff's API:

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.14-slim

# Keep Python's output unbuffered so logs appear immediately in `docker logs`.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy the lockfile first: dependency installation can then be cached
# independently of source-code edits (see 40.3).
COPY requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

# Copy the application. A .dockerignore must exclude .env, .git, data/,
# reports/, virtualenvs, caches, and the frontend.
COPY . .

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

This image works — and is a bad production image: it runs as root, includes build/test dependencies, and bakes every copied file into a layer. Sections 40.6–40.7 fix it.

**Rule of thumb.** The image should contain the interpreter, the runtime dependencies, and the application — nothing you would not hand to a stranger, and nothing that changes per environment.

---

## 40.2 Build vs. Run

**Motivate.** The most common first-container failure is a server that starts correctly and is unreachable. The second is data that vanishes when the container is recreated. Both come from confusing the image with the running container.

**Define.** `docker build` turns a Dockerfile plus context into an image. `docker run` starts a container from it. The image is immutable; the container's writable layer is disposable. Configuration that differs between environments (keys, URLs, tenant IDs) is injected at **run** time, not baked at build time.

**Show.** The lifecycle on WhyTheDiff:

```bash
# Build once, tag with a meaningful version (not just :latest).
docker build -f Dockerfile.api -t whythediff-api:0.1.0 .

# Run it detached, publish the port, inject secrets at runtime.
docker run -d --name whythediff-api \
  -p 8000:8000 \
  --env-file .env \
  -v whythediff-data:/app/data \
  -v whythediff-reports:/app/reports \
  whythediff-api:0.1.0

docker logs -f whythediff-api          # stdout/stderr
docker exec -it whythediff-api sh      # debug shell (disposable)
docker stop whythediff-api             # SIGTERM, then SIGKILL after grace period
docker rm whythediff-api               # writable layer gone; volumes remain
```

Three details that cause real incidents:

- **Bind to `0.0.0.0` inside the container.** A server on `127.0.0.1` is reachable only inside that container's network namespace; publishing the port does nothing. WhyTheDiff's `uvicorn --host 0.0.0.0` is for this reason, not because the host should expose it.
- **Use exec-form `CMD`.** `CMD uvicorn ...` runs through a shell, which becomes PID 1 and may not forward signals. `CMD ["uvicorn", ...]` makes uvicorn PID 1 and lets it shut down cleanly.
- **Containers are cattle, not pets.** Do not `docker exec` into a container to install a package or edit code; rebuild the image. The change disappears on the next deploy, or worse, makes the running artifact unreproducible.

**GPU containers, briefly.** A GPU is hardware, not userspace: install the NVIDIA Container Toolkit on the host and run with `--gpus all`; the CUDA user-space libraries come from a CUDA base image (`nvidia/cuda:*`). WhyTheDiff runs on CPU (local embeddings), so it needs none of this. Reach for it when you serve a model that requires a GPU, and expect multi-gigabyte images.

**Rule of thumb.** Build once, run many, inject environment at run time, and treat every container as replaceable.

---

## 40.3 Layers and Caching

**Motivate.** A rebuild that re-downloads every dependency because you changed one line of Python is not just slow; it makes you avoid rebuilding, which means you deploy stale images. Cache design is developer velocity and correctness at the same time.

**Define.** Each Dockerfile instruction produces a layer. The builder reuses a cached layer when the instruction **and its inputs** are unchanged: the parent layer, the command string, and — for `COPY`/`ADD` — a checksum of the copied files. The first cache miss invalidates every later layer. This is why instruction order determines rebuild time.

**Show.** The difference, on the same app:

```dockerfile
# Slow: every source edit invalidates the dependency install.
COPY . .
RUN pip install -r requirements.lock

# Fast: dependencies are a separate, rarely changing layer.
COPY requirements.lock .
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY . .
```

The same principle applies to the frontend: copy `package.json` and `package-lock.json`, run `npm ci`, then copy the source. `npm ci` (not `npm install`) installs exactly the lockfile and fails if the two files disagree — the right behavior in a build.

Practical rules that follow from the mechanism:

- **Combine `apt-get update` with `apt-get install` in one `RUN`.** A cached `update` layer can otherwise pair with a later `install`, giving you stale packages or a 404.
- **Delete package-manager caches in the same layer.** `rm -rf /var/lib/apt/lists/*` in a later `RUN` does not shrink the image; the earlier layer still contains the files.
- **Use BuildKit cache mounts for package managers** when builds are frequent: `RUN --mount=type=cache,target=/root/.cache/pip pip install ...`. The cache lives outside the image layers.
- **Force freshness deliberately.** `--pull` refreshes the base image; `--no-cache` rebuilds every layer. Rebuild on a schedule, not only when code changes, because base images get security patches.
- **Keep the context small.** The builder receives the whole context before it starts; `.dockerignore` reduces transfer time and prevents accidental copies of `.env`, `.git`, `node_modules`, `data/`, and `reports/`.

**Rule of thumb.** Order instructions from the least frequently changing (base image, system packages, lockfiles) to the most frequently changing (source code). If changing a source file reinstalls dependencies, the Dockerfile is wrong.

---

## 40.4 Volumes

**Motivate.** Delete a container and its writable layer disappears. For WhyTheDiff, that layer contains the vector index, checkpoints, traces, and every saved report — the entire memory of the product. Volumes are how state survives the container lifecycle; the absence of a volume is a data-loss bug waiting for the next deploy.

**Define.** Three mount types, different jobs:

| Type | Where the data lives | Use it for |
|---|---|---|
| **Named volume** | Docker-managed directory on the host | databases, indexes, checkpoints, model caches |
| **Bind mount** | a host path you name | local development: live code, fixtures, a specific data folder |
| **tmpfs** | memory only | scratch files, secrets that must not touch disk |

Named volumes are the default recommendation for application state: Docker manages permissions and location, they work across platforms, and they survive `docker rm`. Bind mounts are convenient for development and dangerous for production because they couple the container to the host's directory layout.

**Show.** WhyTheDiff's state map:

| Container path | Contents | Why it must persist |
|---|---|---|
| `/app/data` | embedded Qdrant, SQLite checkpoints, bundles, traces | losing it loses investigations and resume |
| `/app/reports` | saved report JSON | the product's output |
| `/app/.cache` | FastEmbed/Hugging Face model cache | without it, every recreate re-downloads models |

```bash
docker run -d --name whythediff-api \
  -v whythediff-data:/app/data \
  -v whythediff-reports:/app/reports \
  -v whythediff-models:/app/.cache \
  whythediff-api:0.1.0
```

In Compose, declare the volumes at the bottom and mount them per service:

```yaml
services:
  api:
    volumes:
      - whythediff-data:/app/data
      - whythediff-reports:/app/reports
      - whythediff-models:/app/.cache
volumes:
  whythediff-data:
  whythediff-reports:
  whythediff-models:
```

Two facts worth internalizing. A named volume **persists when its container is removed**, and `docker compose down -v` deletes it — that flag is the difference between "restart" and "wipe the database." And when an empty named volume mounts over a directory that exists in the image, Docker copies the image's contents in; this is how you pre-seed permissions and default files, but it also means an unexpectedly non-empty volume can mask what you thought was in the image.

**Rule of thumb.** If losing it would hurt, it goes in a volume; if it can be rebuilt from code or a download, it does not. Never put a database's storage inside the image or rely on the container's writable layer.

---

## 40.5 Networking Between Containers

**Motivate.** Containers are isolated network namespaces. `localhost` inside the API container means the API container, not your laptop and not the database container. Most "connection refused" incidents in Compose are really a misunderstanding of which namespace a hostname resolves in.

**Define.** Docker creates a **bridge** network by default. Containers on the same user-defined network can reach each other by **service name** through Docker's embedded DNS; the default bridge only gives IPs, not names. `EXPOSE` documents a port inside the network; `ports:` / `-p` publishes it to the host. Traffic between containers does not need publishing at all.

**Show.** The production topology for WhyTheDiff:

```text
browser ──:8080──▶ web (nginx :80) ──/api paths──▶ api (:8000)
                                                   │
                                                   └── embedded Qdrant (same container, local files)
```

Nginx serves the built React files and proxies the API paths to `http://api:8000`. Nothing else is published. If WhyTheDiff later switches from embedded Qdrant to the server, the API talks to `http://qdrant:6333` on the same network — no host port, no credentials in the browser.

```nginx
# frontend/nginx.conf (excerpt)
server {
  listen 80;
  root /usr/share/nginx/html;

  # Server-sent events must not be buffered by the proxy.
  location ~ ^/investigations/[^/]+/events$ {
    proxy_pass http://api:8000;
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    proxy_buffering off;
    proxy_read_timeout 3600s;
  }

  location ~ ^/(health|investigations|reports)(/|$) {
    proxy_pass http://api:8000;
    proxy_set_header Host $host;
  }

  location / {
    try_files $uri $uri/ /index.html;   # SPA fallback
  }
}
```

The SSE block is not decoration: nginx buffers proxied responses by default, and WhyTheDiff's stage log would arrive in bursts at the end instead of streaming. `proxy_buffering off` (plus a long read timeout) fixes it.

Two more controls worth knowing:

- **`internal: true`** creates a network with no route out. Put a database on an internal network and the frontend on both the internal and an external one. This is Step 39's egress allowlist at the container layer.
- **`host.docker.internal`** resolves to the host from a container on Docker Desktop (Windows/macOS); it is how a container reaches a service running natively on your laptop. Do not build production dependencies on it.

**Rule of thumb.** Publish only the edge. Everything else talks service-to-service by name on a user-defined network, and databases never get a public port.

---

## 40.6 Multi-Stage Builds

**Motivate.** Building a React app needs Node and hundreds of megabytes of `node_modules`; running it needs neither. Compiling Python wheels may need `gcc`; serving the app does not. Shipping build tools to production inflates the image, slows every pull, and adds vulnerabilities that can never execute useful code.

**Define.** A multi-stage build has several `FROM` instructions. Each starts a fresh stage; `COPY --from=<stage>` carries only the artifact forward. The final stage becomes the image; earlier stages are discarded. Stages can be named (better than indexes) and targeted (`--target`) for debugging.

**Show.** The frontend is the clearest case:

```dockerfile
# syntax=docker/dockerfile:1
# ---------- build stage ----------
FROM node:22-alpine AS build
WORKDIR /app

# Dependency layer: cached until the lockfile changes.
COPY package.json package-lock.json ./
RUN npm ci

# Source layer: changes often; only this rebuilds on UI edits.
COPY . .
RUN npm run build          # outputs /app/dist

# ---------- runtime stage ----------
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
```

The runtime image contains nginx and static files — no Node, no `node_modules`, no source. The backend gets the same treatment: install the lockfile into a virtualenv in a builder stage, then copy `/opt/venv` into a slim runtime stage. Compilers and pip caches stay behind.

One subtlety specific to Vite: **environment variables are inlined at build time**. `VITE_*` values end up in the JavaScript bundle, so never put a secret there, and remember that changing `VITE_API_URL` requires a rebuild — it is not a runtime setting. WhyTheDiff avoids the problem by using relative API paths, which nginx proxies.

**Rule of thumb.** The final stage should contain the artifact and its runtime. If it contains a compiler, a package manager's cache, or `node_modules`, you are shipping the workshop instead of the furniture.

---

## 40.7 Image Hygiene and Container Security

**Motivate.** An image is a portable copy of your filesystem, and a container is a process with whatever permissions you gave it. Both defaults are generous: root inside the container, a writable filesystem, and a build context that happily includes `.env` if you forgot to exclude it.

**Define.** Image hygiene is the set of choices that keep the artifact minimal and non-secret; container security is the set that limits what a compromised process can do. They overlap at the base image and the user.

**What to do, and why it matters:**

- **`.dockerignore` first.** Exclude `.git`, `.env*`, `.venv`, `node_modules`, `dist`, `__pycache__`, `.pytest_cache`, `data/`, `reports/`, `.cache/`, and any local credentials. This prevents secrets from entering a layer (deleting them in a later `RUN` does **not** remove them from history) and keeps the context small.
- **Run as non-root.** Create a dedicated user, `chown` only the directories it needs, and end the runtime stage with `USER app`. Root in a container is not automatically root on the host, but it turns a container escape or a writable-volume mistake into a much larger problem.
- **Pin the base image.** Tags are mutable; `python:3.14-slim` can resolve to a different image next month. Pin a digest for reproducible production builds (`FROM python:3.14-slim@sha256:...`), and update deliberately with Dependabot or a rebuild schedule.
- **Keep the base minimal.** `slim`/`alpine` variants have fewer packages and fewer CVEs. Install only what the runtime needs; no editors, compilers, or debuggers in the final stage.
- **Never bake secrets.** `ENV` and `ARG` values are visible in image metadata/history; `COPY . .` can bring `.env` along. Inject secrets at run time via `--env-file`, Compose `env_file`, or the platform's secret manager.
- **Scan and rebuild.** Run a scanner (Docker Scout, Trivy) in CI and on a schedule; rebuilding with `--pull` picks up patched base layers.
- **Limit the blast radius.** Drop capabilities (`--cap-drop=ALL`), set `--security-opt=no-new-privileges`, use a read-only root filesystem where the app permits it, set memory/CPU limits, and never mount the Docker socket or run `--privileged` for convenience.
- **Healthcheck the real thing.** Hitting `/health` is a better liveness signal than "the process exists"; orchestrators use it to decide whether to route traffic.

A hardened API stage, building on 40.6:

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.14-slim AS builder
WORKDIR /build
COPY requirements.lock .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --no-cache-dir --require-hashes -r requirements.lock

FROM python:3.14-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    HF_HOME=/app/.cache/huggingface \
    FASTEMBED_CACHE_PATH=/app/.cache/fastembed
RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid app --create-home app
WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app . .
RUN mkdir -p /app/data /app/reports /app/.cache \
 && chown -R app:app /app/data /app/reports /app/.cache
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Note what is **not** here: no `.env` copy, no root user, no compiler in the runtime stage, no `latest`, and no secret in `ENV`. The lockfile currently includes the `dev` and `eval` extras because it was generated with them; a runtime-only lock would shrink the image further. That is a legitimate follow-up, not a correctness bug.

**Rule of thumb.** Assume the image will be pulled, inspected, and run by someone hostile. If `docker history` or `docker save` would reveal it, it does not belong in the image.

---

## 40.8 Docker Compose

**Motivate.** WhyTheDiff is not one process: the API, the static frontend, and (optionally) Qdrant need to start in the right order, on the same network, with the right volumes. Typing three `docker run` commands with matching flags is how environments drift. Compose describes the topology in one file and recreates it with one command.

**Define.** Compose is a YAML front end for containers on one host. A **service** is a container spec (image or build, ports, volumes, environment, healthcheck); Compose creates a network and DNS names for the services, plus any declared volumes. It is excellent for development, CI, and single-host deployments; it is not a cluster orchestrator.

**Show.** A production-shaped `compose.yaml` for WhyTheDiff:

```yaml
name: whythediff

services:
  api:
    build:
      context: .
      dockerfile: Dockerfile.api
    env_file: .env                 # runtime secrets; never baked into the image
    environment:
      DATA_DIR: /app/data
      REPORTS_DIR: /app/reports
    volumes:
      - whythediff-data:/app/data
      - whythediff-reports:/app/reports
      - whythediff-models:/app/.cache
    expose:
      - "8000"                     # internal only; the web service proxies it
    init: true
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"]
      interval: 30s
      timeout: 3s
      retries: 3
      start_period: 25s

  web:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    ports:
      - "8080:80"                  # the only published port
    depends_on:
      api:
        condition: service_healthy
    restart: unless-stopped

volumes:
  whythediff-data:
  whythediff-reports:
  whythediff-models:
```

Day-to-day commands:

```bash
docker compose up -d --build      # build changed images, start the stack
docker compose ps                 # status + health
docker compose logs -f api        # follow one service
docker compose exec api sh        # debug inside the running container
docker compose down               # stop and remove containers; volumes stay
docker compose down -v            # ALSO delete named volumes (destructive)
```

If you want Qdrant as a service instead of embedded mode, add it and give it a volume:

```yaml
  qdrant:
    image: qdrant/qdrant:<pinned-version>   # pin the version you tested; never :latest
    volumes:
      - whythediff-qdrant:/qdrant/storage
    expose: ["6333"]
```

That requires a code seam: `retrieval/clients.py` currently opens `QdrantClient(path=settings.data_dir / "qdrant")`, so the API ignores a Qdrant service until `open_qdrant()` learns to use `QDRANT_URL` when it is set. Do not run embedded mode and a server against the same storage directory — one writer, or corruption.

Compose is also where environment parity is visible: the API reaches Qdrant at `qdrant:6333`, not `localhost:6333`; the browser reaches the app at `localhost:8080`, not `api:8000`. Each name is correct only inside its own namespace.

**Rule of thumb.** One service per concern, healthchecks on anything others depend on, only the edge published, and state in named volumes. If a flag is required to make it work, it belongs in the file.

---

## 40.9 Registries, Tags, and Shipping the Image

**Motivate.** "It works on my machine" evolves into "it works in the image on my machine" unless the *same* image reaches the server. A registry is how the artifact travels; tags and digests are how you prove it is the same one.

**Define.** A registry stores images by repository and reference. `docker tag` adds a name; `docker push` uploads the layers; the server `docker pull`s them. A tag is a mutable pointer (`whythediff-api:0.1.0`, `:latest`); a digest (`sha256:...`) is immutable content. Production deploys should resolve to a digest or an immutable version tag, never to a moving `latest`.

**Show.** Publish to GitHub Container Registry (the natural home for this repo):

```bash
docker login ghcr.io -u <github-user>          # token with package write scope
docker tag whythediff-api:0.1.0 ghcr.io/<owner>/whythediff-api:0.1.0
docker push ghcr.io/<owner>/whythediff-api:0.1.0

# On the server / platform: pull the exact version.
docker pull ghcr.io/<owner>/whythediff-api:0.1.0
docker run ... ghcr.io/<owner>/whythediff-api:0.1.0
```

Tagging conventions that stay useful: a human version (`0.1.0`), a git SHA for traceability (`0.1.0-4f972f5`), and optionally `latest` as a convenience pointer. Do not deploy the convenience pointer.

**GPU containers, briefly.** If the service needs a GPU, install the NVIDIA Container Toolkit on the host, use a CUDA base image compiled for the driver you target, and pass `--gpus all` (or the Compose `deploy.resources.reservations.devices` equivalent). The host driver must be compatible with the container's CUDA user space; the image cannot supply the kernel driver. WhyTheDiff does not need this — local FastEmbed embeddings run on CPU — but the deployment platform must have enough RAM for the model cache.

**Where Docker stops.** Compose runs one host; it does not reschedule a dead container onto another machine, manage rolling deploys, or provide a managed database. Step 41 delegates that to a platform. The image remains the contract: the platform builds or pulls it, injects secrets, and runs it behind a URL.

**Rule of thumb.** Build one artifact, tag it immutably, push it, deploy that reference everywhere. If staging and production run different digests, you have not tested production.

---

## Pitfalls

- **`.env` inside the image.** `COPY . .` plus a missing `.dockerignore` bakes secrets into a layer; deleting the file later does not remove it. Check with `docker history` and `docker save`.
- **Dependencies after source.** `COPY . .` before `pip install`/`npm ci` makes every code edit reinstall everything. Copy lockfiles first.
- **`apt-get update` in its own layer.** The cached update goes stale and installs fail or fetch old packages. Combine update + install + cleanup in one `RUN`.
- **`localhost` inside the container.** The API binds `127.0.0.1`, the port is published, and nothing answers. Bind `0.0.0.0` in the container.
- **No volume for state.** Qdrant storage, SQLite checkpoints, and reports vanish on recreate. Map `/app/data` and `/app/reports`.
- **`docker compose down -v` as a reflex.** It deletes the volumes. Know which command is destructive before running it.
- **Running as root.** A compromised process gets a writable filesystem and unnecessary privileges. Create a user and `USER` it.
- **`latest` in production.** You cannot tell what is deployed or roll back. Use immutable tags/digests.
- **Publishing the database.** `ports: ["6333:6333"]` exposes Qdrant to the host (and possibly the internet). Keep it internal; only nginx publishes.
- **Build tools and dev dependencies in the runtime image.** Bigger pulls, more CVEs, no benefit. Multi-stage it.
- **Nginx buffering SSE.** The stage log arrives all at once or the stream times out. Disable buffering for the events route.
- **Wrong platform.** Building on Apple Silicon for an amd64 server (or vice versa) produces a container that will not start. Build with `--platform` or let the platform build from the Dockerfile.
- **CRLF in entrypoint scripts.** A Windows-edited `entrypoint.sh` with `\r\n` fails with `bad interpreter`. Set LF in `.gitattributes` or run `dos2unix`.
- **Bind mounts in production.** Mounting the host's source over `/app` hides the image's code and reintroduces "works on my machine." Use bind mounts for development only.

---

## Quick Reference

| Command | What it does |
|---|---|
| `docker build -t name:tag .` | build an image from the context |
| `docker build --pull --no-cache -t name:tag .` | fresh base + rebuild every layer |
| `docker run -d -p 8080:80 --env-file .env name:tag` | run detached, publish, inject env |
| `docker ps` / `docker ps -a` | running / all containers |
| `docker logs -f <container>` | follow stdout/stderr |
| `docker exec -it <container> sh` | debug shell inside a running container |
| `docker stop` / `docker rm` | stop gracefully / remove (writable layer) |
| `docker images` | list images and sizes |
| `docker history <image>` | inspect layers and metadata |
| `docker volume ls` / `docker volume prune` | list / remove unused volumes |
| `docker compose up -d --build` | build and start the stack |
| `docker compose down -v` | stop and delete containers **and volumes** |
| `docker tag` / `docker push` | name / upload an image |

| Symptom | Likely cause | Fix |
|---|---|---|
| connection refused after `-p` | server bound to `127.0.0.1` | bind `0.0.0.0` |
| `exec format error` | wrong architecture or CRLF script | build for target platform; convert line endings |
| permission denied on volume | non-root user does not own the mount | `chown` the directory in the image; check UID |
| dependency install reruns every build | source copied before lockfile | reorder `COPY` |
| SSE stalls or arrives at once | proxy buffering | `proxy_buffering off`, long read timeout |
| data gone after redeploy | no volume / `down -v` | mount named volumes; stop using `-v` casually |
| image huge | build tools or dev deps in final stage | multi-stage build, runtime-only lock |
| container exits immediately | command finished or crashed | `docker logs`, check `CMD` and entrypoint |

---

## Theory Summary

- **An image is an immutable artifact; a container is a disposable process.** Everything that must persist lives outside the container, in a volume or an external service.
- **The Dockerfile is code.** Its instruction order determines cache behavior; its `COPY` scope determines what leaks into the artifact; its `USER` determines the blast radius.
- **Build-time and run-time are different worlds.** Dependencies and static assets are baked at build; secrets and environment-specific addresses are injected at run. Vite blurs this line — its `VITE_*` values are build-time.
- **Networks are namespaces.** `localhost` is always "this container"; other services are reached by name on a shared user-defined network; only the edge should be published.
- **Multi-stage builds are how production images stay small.** The build stage may be enormous; the runtime stage should contain the artifact and its interpreter, nothing more.
- **Security is configuration.** Non-root, pinned bases, no secrets in layers, minimal packages, and explicit capabilities are choices, not defaults. Docker packages the app; Step 39's controls constrain what it can do.
- **The registry is the handoff.** Deploy the digest you tested. Tags are labels; digests are identity.
- **Reproducibility is the product.** The same image should produce the same reports, the same eval numbers, and the same failures — on your machine and on the server.

---

## Deliverable

**`Phase 1(AI)/STEP 40/step40-docker/`** — a reference container setup for WhyTheDiff, ready to copy into the project:

- **`Dockerfile.api`** — multi-stage build: a builder installs `requirements.lock` into `/opt/venv`; the runtime is `python:3.14-slim`, runs as a non-root `app` user (UID 10001), creates `/app/data`, `/app/reports`, `/app/.cache`, and exposes a `HEALTHCHECK` against `/health`. `CMD` is exec-form uvicorn on `0.0.0.0:8000`.
- **`Dockerfile.web`** — `node:22-alpine` builds the Vite app with `npm ci && npm run build`; `nginx:1.27-alpine` serves `dist/` with the provided config. No Node in the final image.
- **`nginx.conf`** — SPA fallback to `index.html`, reverse proxy for `/health`, `/investigations`, and `/reports`, and a dedicated SSE location with `proxy_buffering off` and a long read timeout.
- **`compose.yaml`** — `api` + `web`; named volumes for data, reports, and the model cache; `env_file: .env`; `api` internal-only; only `web` publishes `8080:80`; `depends_on` gated on the API healthcheck; an optional, commented `qdrant` service with its own volume.
- **`.dockerignore`** (project root) and **`frontend/.dockerignore`** — exclude `.env`, `.git`, `.venv`, `node_modules`, `dist`, caches, `data/`, `reports/`, and test artifacts. Keep `frontend/` out of the API context or accept a slightly larger context; never include `.env`.
- **`smoke.ps1`** (and `smoke.sh` for Linux/macOS) — builds both images, starts the stack, polls `http://localhost:8080/health` until it returns `ok`, runs one report listing request through nginx, prints `docker compose ps` and image sizes, and optionally tears down. It must fail loudly if the health endpoint never becomes ready.

**Check:** `docker compose config` validates; `docker compose up -d --build` starts both services; `curl http://localhost:8080/health` returns `{"status":"ok",...}` through nginx; the API is not reachable directly on port 8000 from the host; `docker compose exec api id` shows the non-root user; a saved report survives `docker compose down && docker compose up -d`; and `docker compose down -v` is the only command that removes it.

**Design note:** the current app uses embedded Qdrant (`QdrantClient(path=...)`), which is why the reference compose keeps it inside the API container with `/app/data` on a volume. Switching to the Qdrant server is a deliberate follow-up: add `QDRANT_URL` to settings, branch in `open_qdrant()`, enable the compose service, and never point two processes at the same storage directory. The frontend proxy and the SSE configuration are the parts most likely to break silently in Step 41; test them through nginx, not against uvicorn directly.
