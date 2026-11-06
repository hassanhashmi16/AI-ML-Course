# Public WhyTheDiff application

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
- Account menu → Your data explains the current expiry policy and offers
  confirmed account deletion. All sessions are revoked, queued runs cancelled,
  and that account's metadata and research files erased. Running investigations
  must finish first. Cleanup failures persist as tombstones, block sign-in,
  and retry hourly between jobs, including after restart. A workspace lease
  protects files until the job process has closed its clients.
- Optional `RETENTION_DAYS` deletes accounts and research after that many days
  without a sign-in or investigation submission. Zero (the default) disables
  automatic deletion. Cleanup runs hourly between jobs and skips pending runs.
  Set the value deliberately before launch; migration gives existing accounts
  a fresh inactivity window. It is an account inactivity policy, not a per-run TTL.
  Hashed usage reservations survive account deletion for their rolling 24-hour
  limit. Existing operator backups and external provider records are separate.
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

1. Choose the final HTTPS origin, for example `https://whythediff.example.com`.
2. Register a GitHub **OAuth app**, with that homepage and the callback
   `https://whythediff.example.com/auth/callback`.
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
docker compose logs -f whythediff
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
- Choose `RETENTION_DAYS` before accumulating user data and disclose backup
  expiry separately. Test account deletion using a disposable account.
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

## Release preflight and recovery drill

Run `python scripts/check_release.py` inside the release environment. It is
read-only, makes no provider calls, prints no credential values, and exits
nonzero for failed configuration checks. Local HTTP intentionally fails the
final HTTPS check. Passing does not verify hosting persistence or public auth.

Stop the app and wait for its worker to exit before copying the **entire**
`/state` volume to a private backup. It contains account identity, hashed
sessions, research, checkpoints, and indexes; restrict access and define an
expiry. Never put it in a public repository. Do not copy live SQLite/Qdrant
files individually. Preserve file ownership for UID 10001 on restore.

For the drill, restore into a separate volume and isolated instance using
disposable accounts and test provider credentials. Confirm saved reports and
ownership survive, queued jobs remain queued, and formerly running jobs become
interrupted/resumable. Restoring an older backup can resurrect deleted records
and sessions: apply all deletion requests since that backup and revoke restored
sessions before reopening traffic. Keep the production instance stopped until
you have chosen exactly one authoritative state volume.

## A zero-dollar deployment budget

Checked 5 November 2026. The current app needs background CPU, RAM for local
embedding/reranking, and durable storage with SQLite and process-file locking.
A free static frontend alone does not host the application.

The [Hugging Face setup guide](huggingface.md) includes UID 1000 builds and a
fixed startup probe for mounted state, but is not a zero-dollar route: current
documentation requires a paid plan to create a new Docker Space. Real bucket
durability, auth, and worker recovery checks are also still required.

- [Hugging Face Spaces](https://huggingface.co/docs/hub/spaces-overview)
  labels CPU Basic hardware (2 CPU, 16 GB RAM) free of hourly hardware charges,
  but requires a paid plan to create a new Docker Space. The previous claim
  that WhyTheDiff could launch there with no subscription cost was incorrect.
  Default disk is ephemeral and free hardware sleeps. Its
  [storage buckets](https://huggingface.co/docs/hub/en/spaces-storage) provide
  a persistence mechanism, but that does not establish compatibility with this
  app's live SQLite/Qdrant files and process leases. Treat Spaces as a candidate
  requiring a tested storage adaptation, not a ready durable deployment.
- [Render Free](https://render.com/docs/free) cannot attach a persistent disk.
  Do not deploy this local-storage architecture there with promises of durable
  history, quotas, or sessions.
- [Oracle Always Free](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
  offers VMs/storage that could fit the architecture, subject to capacity and
  idle-instance reclamation. [Signup requires a supported card](https://www.oracle.com/cloud/free/faq/).
  Use only Always Free resources; trial credits are temporary. The current
  Linux dependency lock/container has been tested on x86-64, not Ampere ARM;
  do not assume that image works on an ARM free VM without a separate build.
- Hosting on an existing computer can retain the current files without buying
  a VM, but needs a secure public HTTPS route and only stays available while
  the machine and connection are up. Electricity/network costs still apply.

For inference, stay on the [Groq Free plan](https://console.groq.com/docs/billing-faqs)
and check its [organization-wide rate limits](https://console.groq.com/docs/rate-limits).
Use conservative app quotas, for example `DAILY_USER_RUNS=2` and
`DAILY_GLOBAL_RUNS=5`, initially. Run counts do not guarantee token-limit
availability; expect 429s when shared provider limits are exhausted. Do not
enable a paid provider plan or automatic upgrades to make a zero-dollar launch.
No custom domain purchase is required if a suitable host supplies an HTTPS URL.
