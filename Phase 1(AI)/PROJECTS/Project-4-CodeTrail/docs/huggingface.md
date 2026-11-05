# Zero-budget cloud launch candidate

Use a public Docker Space on free **CPU Basic**, with a **private** storage
bucket for account state. Free Spaces can sleep; the next visitor may wait for
startup. This is public access with bounded usage, not an always-awake SLA.
No paid hardware, custom domain, or paid inference plan is required for this
candidate configuration. Platform account creation and actual mount testing
remain external steps; no live deployment has been verified yet.

## Account setup

1. Create a free [Hugging Face account](https://huggingface.co/join), if needed.
2. Create a private Docker Space named `codetrail`, selecting **CPU Basic**.
   Upload/sync the standalone CodeTrail repo source, including its README YAML
   and Dockerfile. Never upload `.env`, `data/`, `reports/`, or caches. Keep the
   Space private while configuring and testing, then make the app public.
3. Create a **private** bucket for this app and attach it read-write at `/state`.
   The public Space and private bucket must have different visibility. Do not
   put sessions, questions, reports, or checkpoints in a public bucket/repo.
4. Confirm that the bucket remains within your account's free allowance and
   that neither paid storage nor paid hardware has been enabled.

Hugging Face currently documents [100 GB private storage for free accounts](https://huggingface.co/docs/hub/en/storage-limits),
including buckets. Check the console's current terms and usage before enabling
anything: free-tier availability is not a billing guarantee for another plan.

## Space configuration

Set public **Variables** in Space Settings:

| Variable | Value |
| --- | --- |
| `RUNTIME_UID` | `1000` (build-time; rebuild after setting) |
| `PUBLIC_APP` | `true` |
| `APP_ORIGIN` | The Space's direct `https://…hf.space` origin, without a trailing slash |
| `DATA_DIR` | `/state/data` |
| `REPORTS_DIR` | `/state/reports` |
| `DAILY_USER_RUNS` | `2` initially |
| `DAILY_GLOBAL_RUNS` | `5` initially |
| `MAX_QUEUED_RUNS` | `5` initially |
| `MAX_JOB_SECONDS` | `600` |
| `RETENTION_DAYS` | `30` if you accept deletion after 30 inactive days |

Set **Secrets**, never public Variables: `OAUTH_CLIENT_SECRET`, `GROQ_API_KEY`,
and optionally a public-read-only `GITHUB_TOKEN`. Set `OAUTH_CLIENT_ID` as a
Variable. Register a separate production GitHub OAuth app with homepage equal
to `APP_ORIGIN` and callback `APP_ORIGIN/auth/callback`. Keep the local OAuth
app for development. The generated direct origin is the one to share and test;
embedded frames can restrict cookies.

`RUNTIME_UID=1000` matches [Spaces' runtime user](https://huggingface.co/docs/hub/en/spaces-sdks-docker).
The normal Docker/Compose build still defaults to UID 10001. Do not change an
existing volume's user ID without adjusting ownership. Model caches default
to `/state/.cache`; monitor total storage and cold-start time.

## Prove persistence before opening access

While the Space is still private, set the Variable `STORAGE_PROBE=init`.
Restart it and check the startup logs for `Storage probe passed`. The API starts
only after the probe succeeds. Then set `STORAGE_PROBE=verify`, which restarts
the Space; the logs must show another pass using the same mounted fixture.
Keep `verify` enabled through a manual stop/start and confirm another pass.
Remove the Variable after testing. `init` intentionally refuses to overwrite an
existing probe, so do not leave it enabled across restarts.

If you also have a runtime shell, these are the equivalent diagnostic commands:

```sh
python scripts/probe_storage.py --init
python scripts/check_release.py
```

Restart the Space, then run:

```sh
python scripts/probe_storage.py --verify
```

The probe only creates a small disposable fixture at `DATA_DIR/.storage-probe`.
It checks concurrent SQLite commits, exclusive locks, Qdrant close/reopen,
and a marker across restart. It makes no model calls and does not read accounts.
The startup hook accepts only those two fixed diagnostics; it exposes no web
command-execution endpoint. Do not claim the local container probe tests the
actual Hugging Face mount.

Use only one Space instance. Also perform the real sign-in, cross-account URL,
queue, job-interruption/resume, deletion, backup/restore, and provider-429 checks
in [the release guide](deployment.md). Check the proxy's Host preservation and
client-IP forwarding; per-account/global quotas remain the primary provider
budget boundary until the trusted proxy path is verified.

The mount is a candidate, not a proven drop-in database disk. Hugging Face
[supports bucket volumes](https://huggingface.co/docs/hub/en/spaces-storage)
and [marked a reported SQLite contention issue fixed](https://github.com/huggingface/hf-mount/issues/103).
If this app's probe, hard-restart durability, or job-recovery tests fail on the
actual mount, keep the release private and move durable state to a database/
storage service with suitable guarantees before launch. Do not silently accept
lost history or quota resets just to obtain a free URL.
