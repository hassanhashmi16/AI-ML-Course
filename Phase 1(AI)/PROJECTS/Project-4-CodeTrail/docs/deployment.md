# Public CodeTrail application

This release supports public registration with GitHub, account-private reports
and findings, a durable investigation queue, and live progress. It is designed
for **one server, one application process, and one investigation worker**.
It is an initial public release architecture, with bounded throughput.

## What is implemented

- GitHub authorization-code sign-in with PKCE, single-use expiring state, and
  an HttpOnly session cookie. OAuth is used only to establish identity. It
  requests no repository scopes, and the OAuth token is not stored.
- HTTPS origin validation, same-origin checks on mutating requests, session
  revocation on logout, response security headers, and request-body limits.
- Authenticated access and ownership checks on every job, report, resume, and
  event stream. Another account's identifier returns 404. Local CLI artifacts
  are not imported into public accounts.
- Account-scoped source caches, vector indexes, findings, checkpoints, reports,
  and traces under `DATA_DIR/users/<GitHub numeric id>/`.
- Public-only repository checks even when the server's GitHub token can see
  private repositories. Use a token limited to public reads anyway.
- Durable SQLite job admission and a single background worker. Requests return
  202 with a run identifier immediately. Events stream during execution.
- One pending/active job per account, bounded global queue, rolling 24-hour
  account/global run reservations, per-IP request limits, and bounded inputs.
  Resuming a run consumes another reservation. Failed runs also consume one.
- A process lock refuses a second worker on the same database. Running jobs
  become resumable interrupted jobs after a restart; queued jobs remain queued.
- Provider request timeouts, bounded output tokens, and the existing agent
  budgets. `MAX_JOB_SECONDS=600` caps the whole worker process, including
  collection and indexing. A timed-out job is interrupted and can be resumed.
  These are not a precise monetary spending meter: provider token
  reporting and some graph accounting remain incomplete. Configure provider
  account spending limits as a separate operational control.

All signed-in users can investigate public repositories; no shared password or
invite list is required. They do not receive access to other accounts' questions
or reports. The server operator can access the underlying storage. Questions and
public source excerpts are sent to the configured model provider.

## Configure sign-in

1. Choose the final HTTPS origin, for example `https://codetrail.example.com`.
2. Register a GitHub **OAuth app**, with that homepage and the callback
   `https://codetrail.example.com/auth/callback`.
3. Set `APP_ORIGIN`, `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, and `GROQ_API_KEY`
   in the deployment's secret/environment settings. Set `GITHUB_TOKEN` to a
   public-read-only token for useful GitHub API capacity.
4. Start conservatively with `DAILY_USER_RUNS=5`, `DAILY_GLOBAL_RUNS=30`, and
   `MAX_QUEUED_RUNS=20`. Adjust these after measuring actual server load and cost.

`PUBLIC_APP=true` fails startup without OAuth credentials. It requires an HTTPS
origin except for local `localhost` / `127.0.0.1` testing. Do not expose the
original `PUBLIC_APP=false` local API to the internet.

Official references: [GitHub scopes](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/scopes-for-oauth-apps)
and [GitHub OAuth flow](https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps).

## Build and run

From the project directory, configure the environment values above, then:

```powershell
docker compose up --build -d
docker compose logs -f codetrail
```

The multi-stage Dockerfile builds React and serves the bundle through FastAPI.
It installs the separate **Linux** hash lock; the existing Windows lock includes
Windows-only packages and is not used in Linux images. Base images are pinned
by digest. The runtime is non-root and Compose uses a read-only root filesystem,
no added capabilities, memory/CPU limits, and a persistent `/state` volume.
Do not run `docker compose down -v` against a deployment whose state you need.

Place an HTTPS reverse proxy in front of `127.0.0.1:8000`. Preserve the original
Host header and disable response buffering for `/investigations/*/events`.
The container does not trust forwarded client-IP headers by default. For a
trusted reverse proxy, override the command to use `--proxy-headers` and an
explicit `--forwarded-allow-ips=<proxy-IP>`; never trust arbitrary internet
forwarders. Otherwise the per-IP limiter sees the proxy's single address.
Set proxy request limits and timeouts too. The queued POSTs return quickly;
SSE connections must be allowed to remain open during a run.
Keep query strings out of proxy access logs, particularly on `/auth/callback`;
the image disables Uvicorn access logging to avoid retaining OAuth codes.

First investigations download CPU embedding/reranking models into persistent
`/state/.cache`; plan for disk space and cold-start latency. Start with at least
the Compose allocation (2 CPU / 3 GB memory) and measure the actual workload.

## Before announcing the URL

- Complete a real GitHub sign-in on the deployed HTTPS origin. Check that
  callback configuration and Secure cookies work through the actual proxy.
- Use two accounts: start a run, verify live progress and saved reports, and
  verify the other account cannot read its job/report/event endpoints.
- Check queue/full/quota responses, model/provider outages, and crash-resume.
- Set provider spending caps; monitor queue length, errors, latency, CPU/RAM,
  and remaining disk. Back up the state volume while the app is stopped.
- Choose a retention/deletion policy before accumulating user data; automatic
  account deletion and scheduled retention cleanup are not implemented yet.
- Test restore from backup and restart on the actual host. Run only one server
  process; this SQLite/local-Qdrant design is not a multi-replica deployment.

For higher traffic, migrate admission/auth metadata to PostgreSQL, use a shared
queue and service Qdrant, and make storage and rate limits independent of one
server. That is a scaling project, not a prerequisite to testing this bounded
single-server public beta.

## Remaining external setup

The source code does not create a GitHub OAuth application, buy a domain,
provision a host, configure HTTPS, or set the provider's billing caps. Those
need the owner's hosting/provider accounts and chosen URL. Mocked OAuth tests
and local container checks do not substitute for the deployed checks above.
