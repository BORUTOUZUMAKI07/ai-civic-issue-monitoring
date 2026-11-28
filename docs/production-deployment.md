# Free-tier deployment: Render + Vercel + Neon + Upstash + Prefect

This is the single deployment path for CivicPulse. Everything is on a free tier:

```text
Users
  ├── https://civicpulse-civic-ai8.vercel.app        Next.js frontend + /api/proxy BFF (Vercel Hobby)
  └── wss://civicpulse-api-wknx.onrender.com/api/v1/ws/issues
                                             WebSocket directly to FastAPI

`civicpulse.vercel.app` belongs to a different Vercel project, so this deployment
uses the team's stable production alias above. Vercel Authentication is disabled
on the project so that alias is publicly reachable.

Render free web services
  ├── civicpulse-api               BACKEND_URL for the Vercel BFF
  └── civicpulse-otel-collector    OTLP receiver; owns the New Relic license key

FastAPI backend ──OTLP/HTTP──> collector ──OTLP/HTTP──> New Relic
  ├── Neon Postgres       users, issues, wards, admin, idempotency
  ├── Upstash Redis free  sessions, refresh tokens, rate limits, pub/sub
  ├── MongoDB Atlas free  audit/compliance logs
  ├── Neon Object Storage uploaded images
  └── Prefect Cloud free  cron/background flows
```

## Free-tier tradeoffs — read this first

- Render free web services **spin down after 15 minutes of no traffic**. The next
  request takes about a minute to wake the service. WebSockets disconnect when
  the instance spins down.
- Render free services support **one instance only**. That is fine: the
  WebSocket pub/sub code is already written, but there is only one instance to
  fan out to. If you later move to a paid Render plan, set `numInstances: 2`; no
  code change is needed because Upstash TCP supports `SUBSCRIBE`.
- The separate collector is also free, so it sleeps too. Telemetry emitted
  while it wakes can be dropped; this is accepted, and observability remains
  fail-open. Upgrading only the collector to a paid plan would remove that gap.
- Use the **Upstash TCP** `rediss://...` URL as `REDIS_URL`. Do **not** use the
  HTTPS REST URL/token in production: REST can `PUBLISH` but cannot `SUBSCRIBE`,
  which would silently disable cross-instance WebSocket fan-out.
- The hosted Neon database is already bootstrapped. Do **not** run `create-admin`
  again. New Alembic revisions (currently head `012_user_invariants`) are applied
  automatically by the image's startup command.

If you pasted the Upstash token anywhere public, rotate the database credentials
before using it. Never commit or print secret values.

---

## 1. Where every key goes

No value below belongs in Git. `render.yaml` uses `sync: false` for secrets;
Render prompts for them when the Blueprint is first created.

### Render → backend service (`civicpulse-api`)

First creation: fill the prompts on the **Blueprint creation screen**.
Later changes: **Render Dashboard → civicpulse-api → Environment → Environment Variables**.

| Variable | Value / source |
| :--- | :--- |
| `DATABASE_URL` | Neon pooled Postgres connection string |
| `REDIS_URL` | Upstash **TCP** URL (`rediss://...`), not the HTTPS REST URL |
| `MONGODB_URI` | MongoDB Atlas SRV connection string |
| `SECRET_KEY` | Fresh random 32+ character JWT signing secret |
| `AWS_ENDPOINT_URL_S3` | Neon Storage endpoint from Connect → Storage |
| `AWS_ACCESS_KEY_ID` | Neon Storage access key ID |
| `AWS_SECRET_ACCESS_KEY` | Neon Storage secret access key |
| `OTLP_AUTH_USER`, `OTLP_AUTH_PASSWORD` | The **same** generated Basic-auth pair entered on the collector |

Already set in `render.yaml`, so do not re-enter unless you change them later:

| Variable | Value |
| :--- | :--- |
| `ENVIRONMENT` | `production` |
| `COOKIE_SECURE` | `true` |
| `FRONTEND_URL` | `https://civicpulse-civic-ai8.vercel.app` |
| `CORS_ORIGINS` | `https://civicpulse-civic-ai8.vercel.app` |
| `STORAGE_BACKEND` | `s3` |
| `NEON_STORAGE_BUCKET` | `uploads` |
| `AWS_REGION` | `us-east-2` |
| `MONGODB_DB` | `civicpulse_analytics` |
| `NEW_RELIC_ENABLED` | `true` |
| `NEW_RELIC_OTLP_ENDPOINT` | `https://civicpulse-otel-collector.onrender.com` |
| `NEW_RELIC_EXPORT_INTERVAL_SECONDS` | `5` |
| `NEW_RELIC_APP_NAME` | `CivicPulse-API` |

`NEW_RELIC_OTLP_HEADERS` must be **absent**: the backend never holds the vendor
key. If Render shows a different hostname for the collector service (a suffix
may be added when the name is already taken globally), replace
`NEW_RELIC_OTLP_ENDPOINT` with the exact hostname shown, without a `:4318`
suffix — Render maps public HTTPS to its injected `$PORT`.

### Render → collector service (`civicpulse-otel-collector`)

First creation: fill the prompts on the **Blueprint creation screen**. Later
changes: **Render Dashboard → civicpulse-otel-collector → Environment → Environment Variables**.

| Variable | Value / source |
| :--- | :--- |
| `NEW_RELIC_LICENSE_KEY` | New Relic ingest license key (vendor key; collector-only) |
| `OTLP_AUTH_USER`, `OTLP_AUTH_PASSWORD` | The **same** generated Basic-auth pair entered on the backend |

Already set in `render.yaml`:

| Variable | Value |
| :--- | :--- |
| `ENVIRONMENT` | `production` |
| `SERVICE_VERSION` | `unknown` |
| `NEW_RELIC_APP_NAME` | `CivicPulse-API` (same as backend; alert queries filter on it) |

Do **not** set `PORT` manually. Render injects it, and the tracked collector
config binds its public OTLP/HTTP listener to `${env:PORT}`. Hard-coding `4318`
would make the service unreachable through Render's HTTPS mapping. The
collector's `/healthz` stays internal on `:13133`, so no `healthCheckPath` is
configured; Render checks the injected port directly.

Important: if `UPSTASH_REDIS_REST_URL` or `UPSTASH_REDIS_REST_TOKEN` exist in
Render's Environment tab from an older setup, **delete them**. They switch the
backend to REST-only Redis, which cannot subscribe.

Optional Render variables, only when you actually use those services:

| Variable | Purpose |
| :--- | :--- |
| `OPENAI_BASE_URL`, `OPENAI_MODEL`, `OPENAI_API_KEY` | Groq/OpenAI classifier. Without a key the app falls back to keyword classification. |
| `HF_TOKEN` | HuggingFace embeddings. |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google OAuth. |
| `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` | GitHub OAuth. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM`, `ALERT_EMAIL_TO` | Password reset and drift alerts. |
| `NEW_RELIC_*`, `OTLP_*` | Observability keys above; see `docs/new-relic-alerts.md` for alerts and runbooks. |

### Vercel → frontend project

Location: **Project → Settings → Environment Variables**.

| Variable | Value |
| :--- | :--- |
| `BACKEND_URL` | `https://civicpulse-api-wknx.onrender.com` |
| `NEXT_PUBLIC_API_URL` | `https://civicpulse-api-wknx.onrender.com` |

Both are the public Render backend URL. Vercel cannot reach a private service
name, and the browser needs the public URL for WebSockets.
`NEXT_PUBLIC_API_URL` is baked into the client bundle at build time, so set it
before building/deploying.

### Prefect Cloud → Secret blocks

`prefect/deploy.py` reads local `prefect/.env` and creates these Secret blocks.
It stores block **references** on deployments, never literal secret values.

| `prefect/.env` key | Prefect Secret block |
| :--- | :--- |
| `CIVICPULSE_DB_URI` | `civicpulse-db-uri` |
| `CIVICPULSE_MONGO_URI` | `civicpulse-mongo-uri` |
| `DAGSHUB_TOKEN` | `dagshub-token` |
| `GITHUB_TOKEN` (or `GH_TOKEN`) | `github-token` |
| `SMTP_PASS` | `smtp-pass` |
| `SLACK_WEBHOOK_URL` | `slack-webhook-url` |

`CIVICPULSE_DB_URI` must be a plain `postgresql://` URI. The Neon pooled URL is
already in that form and works with the psycopg2 driver Prefect installs.

`GITHUB_TOKEN` is a GitHub PAT with `repo` scope (Actions dispatch + private
source checkout). Prefect pulls flow code from the canonical GitHub repository,
not the DagsHub mirror, and uses the PAT to send a `repository_dispatch` event
that starts the training workflow. `DAGSHUB_TOKEN` remains DagsHub-only (MLflow
and DVC artifacts). Never put either token in `job_variables.env` as a literal.

### Local development only

`backend/.env` is local and gitignored. Keep:

```text
REDIS_URL=redis://localhost:6379
UPSTASH_REDIS_REST_URL=
UPSTASH_REDIS_REST_TOKEN=
```

To test against Upstash locally, set `REDIS_URL` to the TCP URL and leave the
two REST variables empty.

---

## 2. Automatic deployment on push to main

`.github/workflows/production-deploy.yml` deploys production **after CI succeeds**
on `main`:

```text
push to main → CI (all gates green) → Deploy production → Render collector + backend + Vercel
```

It uses `workflow_run`, not a second `push` trigger, so a red or cancelled CI
run can never deploy. CI already cancels superseded runs; the workflow also
skips a CI commit that is no longer the tip of `main`, leaving that deploy to
the newer CI run.

### Required GitHub secrets

Repository → Settings → Secrets and variables → Actions → New repository secret.

| Secret | Where to get it |
| :--- | :--- |
| `COLLECTOR_DEPLOY_HOOK_URL` | Render → `civicpulse-otel-collector` → Settings → Deploy → Deploy Hook (`https://api.render.com/deploy/...`) |
| `RENDER_DEPLOY_HOOK_URL` | Render → `civicpulse-api` → Settings → Deploy → Deploy Hook |
| `VERCEL_DEPLOY_HOOK_URL` | Vercel → canonical frontend project → Settings → Git → Deploy Hooks → create a hook for branch `main` |

All three URLs are credentials. Never commit them or paste them into an issue.
The workflow checks for them before contacting any platform and fails with a
named error if one is missing; it never prints the values. The collector hook
fires first so its cold start begins as early as possible.

The hooks are branch-scoped: both Render services track `main`, and the Vercel
hook is created for `main`. The workflow additionally appends `ref=<validated
SHA>` to both Render hook requests, so those builds are pinned to the exact CI
commit rather than merely the current branch tip. Vercel's branch-scoped hook
does not take that parameter. Do **not** enable Git auto-deploy on either
Render service or Vercel Git deployment for that branch, or one push will start
duplicate deploys. `render.yaml` sets `autoDeployTrigger: "off"`; Vercel's
`vercel.json` sets `git.deploymentEnabled: false`.

### Manual re-trigger

Actions → **Deploy production** → Run workflow. This deploys the current `main`
tip without a new commit, which is useful after a transient hook failure. The
automatic path always requires CI to be green. There is no staging target; the
old manual SSH deploy workflow was removed. All three hooks are treated as
accepted on any HTTP 2xx response; Vercel returns `201` with a pending job.

### Verify after a deploy

```text
Render → civicpulse-otel-collector → Live, logs contain "Everything is ready"
GET https://civicpulse-api-wknx.onrender.com/health           → 200
GET https://civicpulse-api-wknx.onrender.com/health/telemetry → 200
GET https://civicpulse-civic-ai8.vercel.app                   → 200
```

Render free services sleep after 15 minutes, so the first request may take a
minute to wake the backend (and the collector separately). A telemetry status
of `degraded` immediately after a cold start can be that accepted wake window;
check the collector logs before assuming an auth or key problem. For the full
authenticated checks, run
`gh workflow run smoke.yml` with `base_url=https://civicpulse-civic-ai8.vercel.app`
once the collector and backend are Live and the frontend build is `READY`.

---

## 3. Deploy order

### Step 1 — Push the production files

```powershell
git add -A
git status --short   # confirm no .env files are staged
git commit -m "chore: free-tier Render blueprint and Upstash TCP Redis"
git push github main
```

Use the `github` remote, not `origin`.

### Step 2 — Render backend + collector

1. Dashboard → **New** → **Blueprint**.
2. Connect this GitHub repository, branch `main`.
3. The Blueprint creates two **free** web services: `civicpulse-api` and
   `civicpulse-otel-collector`.
4. Fill every prompted secret from both Render tables above.
   - For `REDIS_URL`, paste the Upstash **TCP** `rediss://...` URL.
   - Do not paste the HTTPS REST URL.
   - Enter the **same** `OTLP_AUTH_USER` / `OTLP_AUTH_PASSWORD` pair on both
     services. A mismatch rejects every signal with HTTP 401.
   - The New Relic license key is entered only on the collector.
5. Delete `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` if they exist.
6. If either service already exists, a deploy hook does **not** apply changed
   Blueprint env values. Use **Sync Blueprint**, then confirm the Environment
   tab, or update the variables manually. This is required for the backend's
   `NEW_RELIC_OTLP_ENDPOINT` change to take effect.
7. The backend image `CMD` runs migrations and then uvicorn:

   ```text
   python -m alembic -c /app/alembic.ini upgrade head && exec uvicorn ...
   ```

   This replaces `preDeployCommand`, which is paid-only on Render, and avoids
   Render's `dockerCommand` shell-parsing issue. Since the DB is already at
   Alembic head, migrations are normally a no-op.

Verify after deploy (use the exact URL Render shows on the service page):

```text
GET https://civicpulse-api-wknx.onrender.com/health           → 200
GET https://civicpulse-api-wknx.onrender.com/health/telemetry → 200
GET https://civicpulse-api-wknx.onrender.com/api/v1/ml/info   → model_type: onnx
```

`/health/telemetry` is diagnostic only: observability is fail-open, so a broken
sink never removes a working instance from rotation. After a warm collector its
`status` should be `ok`, with `traces_ok`, `metrics_ok` and `logs_ok` all true.
Production sends all three signals through the dedicated Render collector,
which owns the vendor key; a cold collector may drop the first startup proof.
See [ADR-0010](adr/0010-render-collector-topology.md) (superseding
[ADR-0009](adr/0009-direct-otlp-ingest.md)) for the decision and
`docs/new-relic-alerts.md` for the matching alerts and runbooks.

The built image contains `/app/models/model.onnx`, so production uses the
trained ONNX model.

Before testing uploads, set CORS on the Neon `uploads` bucket so the browser can
PUT directly to it:

```json
[
  {
    "AllowedOrigins": ["https://civicpulse-civic-ai8.vercel.app", "http://localhost:3000"],
    "AllowedMethods": ["PUT"],
    "AllowedHeaders": ["content-type"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 3600
  }
]
```

The bucket stays private. Users still fetch images through the authenticated
`/api/proxy/issues/media/...` route; only the write is presigned.

### Step 3 — Vercel frontend

1. Import the same GitHub repo.
2. Set **Root Directory** to `frontend`.
3. Set the two env vars above for Production (and Preview if you want previews).
4. Deploy. `frontend/vercel.json` sets the Next.js preset and build command.

Register these real OAuth callback URLs with Google/GitHub:

```text
https://civicpulse-civic-ai8.vercel.app/api/proxy/auth/oauth/google/callback
https://civicpulse-civic-ai8.vercel.app/api/proxy/auth/oauth/github/callback
```

### Step 4 — Prefect Cloud

1. Fill local `prefect/.env` with the values in the Prefect table above.
2. Authenticate: `prefect cloud login`.
3. Verify connectivity:

```powershell
pixi run -e prefect prefect-check-connections
```

4. Create/update the managed work pool, Secret blocks, 5 deployments, and 2 automations:

```powershell
pixi run -e prefect prefect-deploy
```

DagsHub S3 remains the DVC/ML artifact remote. It is not used for app uploads.

---

## 4. Bootstrap status — already done, do not repeat

The hosted Neon database was verified locally:

- Alembic head: `012_user_invariants` (the manual bootstrap check was at
  `011_auth_hardening_email_gdpr`; revision 012 is applied by the image on the
  next deploy, and enforces a single super admin plus unique OAuth identities)
- Wards: `19`
- Super admins: exactly `1` (`ram.atchutratna@gmail.com`)
- Neon `uploads` bucket: reachable

Do **not** run `create-admin` on Render. It is a one-time bootstrap, and
rerunning it with a different email would create a second super admin. Later
admins should be created through the existing admin API.

---

## 5. Scale fixes already implemented

- **WebSockets:** every event is published once to Redis
  (`civicpulse:issue-updates`); each backend instance has a subscriber that
  delivers to its own sockets. Events from the publishing instance are tagged
  and ignored by that instance's subscriber, so no client gets duplicates.
  Free Render runs one instance, but the code is ready for `numInstances: 2`
  after a paid upgrade because Upstash TCP supports `SUBSCRIBE`.
- **Uploads past the Vercel cap:** `POST /api/v1/uploads/presign` returns a
  15-minute signed PUT URL for one random object key plus an HMAC token bound to
  that key, user, and purpose. The browser PUTs bytes straight to Neon; the BFF
  receives only a few KB of JSON and the key/token, then the backend reads the
  bytes from storage for validation and ML inference. Stored URLs keep the
  `/uploads/issues/...` and `/uploads/resolutions/...` shape, so authenticated
  media viewing is unchanged. Local development without S3 falls back to the
  old multipart path automatically.
- **OAuth/SMTP:** real consent screens and real mail delivery are still
  unverified until actual credentials are configured and tested.

---

## 6. Security rule

Public: frontend URL and backend API URL.

Never public: database, Redis, MongoDB, admin password, `SECRET_KEY`, SMTP
password, OAuth client secret, object-storage keys, `NEW_RELIC_LICENSE_KEY`, or
the `OTLP_AUTH_*` pair. A public backend/collector URL is normal; it is not the
same as exposing the database, and the collector receiver requires Basic auth.
