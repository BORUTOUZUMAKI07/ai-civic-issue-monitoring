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

Render free web service
  └── BACKEND_URL=https://civicpulse-api-wknx.onrender.com for the Vercel BFF

FastAPI backend
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
| `NEW_RELIC_OTLP_HEADERS` | JSON object `{"api-key":"<New Relic license key>"}` |
| `OTLP_AUTH_USER`, `OTLP_AUTH_PASSWORD` | Generated Basic-auth pair for the OTLP handshake |

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
| `NEW_RELIC_OTLP_ENDPOINT` | `https://otlp.nr-data.net:4318` |
| `NEW_RELIC_EXPORT_INTERVAL_SECONDS` | `5` |
| `NEW_RELIC_APP_NAME` | `CivicPulse-API` |

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
push to main → CI (all gates green) → Deploy production → Render + Vercel
```

It uses `workflow_run`, not a second `push` trigger, so a red or cancelled CI
run can never deploy. CI already cancels superseded runs; the workflow also
skips a CI commit that is no longer the tip of `main`, leaving that deploy to
the newer CI run.

### Required GitHub secrets

Repository → Settings → Secrets and variables → Actions → New repository secret.

| Secret | Where to get it |
| :--- | :--- |
| `RENDER_DEPLOY_HOOK_URL` | Render → `civicpulse-api` → Settings → Deploy → Deploy Hook (`https://api.render.com/deploy/...`) |
| `VERCEL_DEPLOY_HOOK_URL` | Vercel → canonical frontend project → Settings → Git → Deploy Hooks → create a hook for branch `main` |

Both URLs are credentials. Never commit them or paste them into an issue. The
workflow checks for them before contacting either platform and fails with a
named error if one is missing; it never prints the values.

The hooks are branch-scoped: Render's service tracks `main`, and the Vercel hook
is created for `main`, so each deploy builds the current `main` tip. Do **not**
also enable platform-native auto-deploy for that branch, or one push will start
two deploys.

### Manual re-trigger

Actions → **Deploy production** → Run workflow. This deploys the current `main`
tip without a new commit, which is useful after a transient hook failure. The
automatic path always requires CI to be green.

### Verify after a deploy

```text
GET https://civicpulse-api-wknx.onrender.com/health           → 200
GET https://civicpulse-api-wknx.onrender.com/health/telemetry → 200
GET https://civicpulse-civic-ai8.vercel.app                   → 200
```

Render free services sleep after 15 minutes, so the first request may take a
minute to wake the backend. For the full authenticated checks, run
`gh workflow run smoke.yml` with `base_url=https://civicpulse-civic-ai8.vercel.app`
once both builds are `READY`.

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

### Step 2 — Render backend

1. Dashboard → **New** → **Blueprint**.
2. Connect this GitHub repository, branch `main`.
3. The Blueprint creates only `civicpulse-api` on the **free** plan.
4. Fill every prompted secret from the Render table above.
   - For `REDIS_URL`, paste the Upstash **TCP** `rediss://...` URL.
   - Do not paste the HTTPS REST URL.
5. Delete `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` if they exist.
6. The image `CMD` runs migrations and then uvicorn:

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
sink never removes a working instance from rotation. After a fresh deploy its
`status` should be `ok`, with `traces_ok`, `metrics_ok` and `logs_ok` all true.
Production exports directly to New Relic's OTLP/HTTP ingest — there is no
Render-hosted collector to wake after idle. The collector in `docker/` is a
local-Compose-only tool; see
[ADR-0009](adr/0009-direct-otlp-ingest.md) for the decision and
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
password, OAuth client secret, or object-storage keys. A public backend URL is
normal; it is not the same as exposing the database.
