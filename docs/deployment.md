# Deployment & Release

The canonical production runbook is
[`docs/production-deployment.md`](production-deployment.md).

Production deployment is automatic:

```text
push to main -> CI (all gates green) -> Deploy production -> Render collector + backend + Vercel
```

`.github/workflows/production-deploy.yml` is the only deploy workflow. It is
production-only; there is no staging target and no environment dropdown.

| Workflow | Purpose |
| :--- | :--- |
| `ci.yml` | Tests, security gates, and GHCR image publishing |
| `production-deploy.yml` | CI-gated production deploy to Render collector + backend and Vercel frontend |
| `smoke.yml` | Manual verification against a deployed frontend URL |
| `train.yml` | Prefect-triggered model retraining |

## Git remotes

The canonical application repository is GitHub. In a clean clone, rename the
remote that `git clone` creates so app code always goes to GitHub:

```bash
git clone https://github.com/BORUTOUZUMAKI07/ai-civic-issue-monitoring.git
cd ai-civic-issue-monitoring
git remote rename origin github
```

In this project `origin` is reserved for the DagsHub **ML/DVC artifact** mirror
(`https://dagshub.com/ram.atchutratna/ai-civic-issue-monitoring.git`). DVC also
has its own remote named `origin` in `.dvc/config`, pointing at DagsHub S3; that
is artifact storage only and must never receive application uploads. If you add
the DagsHub git mirror locally, use:

```bash
git remote add origin https://dagshub.com/ram.atchutratna/ai-civic-issue-monitoring.git
git remote -v   # github -> GitHub (code); origin -> DagsHub (ML/DVC)
```

**Never run `git push origin` for app code.** Use `git push github` everywhere.

## Images

CI publishes immutable images tagged with the commit SHA plus `:latest` for the
current `main` tip:

```text
ghcr.io/<owner>/<repo>/backend:<sha>
ghcr.io/<owner>/<repo>/frontend:<sha>
```

`<owner>/<repo>` is lower-cased because GHCR requires lowercase repositories.
Tagged releases additionally try DockerHub when `DOCKERHUB_USERNAME` and
`DOCKERHUB_TOKEN` are configured; missing credentials skip that publish without
failing the release.

## Deployed smoke checks

Run these once the collector and backend are Live and the frontend build is `READY`:

```bash
gh workflow run smoke.yml \
  --repo BORUTOUZUMAKI07/ai-civic-issue-monitoring \
  -f base_url=https://civicpulse-civic-ai8.vercel.app
```

The script goes through the Next.js BFF: frontend `GET /`, OAuth providers,
one-time code rejection, login -> `/auth/me` -> refresh, and optional admin
audit checks when `SMOKE_ADMIN_*` secrets are set. Use a dedicated low-privilege
smoke account; never put a real user's password in these secrets.

The smoke deliberately does not attempt a real Google/GitHub consent flow or
send real email: those need interactive provider accounts and a working SMTP
relay. Verify them separately in the deployed environment.

## Seed data and the first admin

Two one-off steps run against the target database; the backend image ships
neither `backend/scripts/` nor a way to create an admin through the API.

**1. Ward seeding** — run locally with `backend/.env` pointing at the target DB:

```bash
pixi run seed        # runs scripts/seed_wards.py
```

**2. The first admin** — the public API only registers `field_worker`/`viewer`
accounts and only a `super_admin` can promote anyone, so a fresh database cannot
reach the admin console at all. Bootstrap it locally (same `backend/.env`) **only
on a fresh, empty database**:

```bash
ADMIN_EMAIL=you@example.com ADMIN_PASSWORD='<at-least-12-chars>' pixi run create-admin

# use ADMIN_ROLE=super_admin for the top-level account
```

The script (`backend/scripts/create_admin.py`) inserts the user through the
app's own models and password hashing. It refuses to create a second
`super_admin`: exactly one is enforced by migration `012` and a startup
preflight. **Do not rerun it against hosted production.** The production super
admin already exists; create further admins through the authenticated admin
API. See
[`docs/production-deployment.md`](production-deployment.md#4-bootstrap-status--already-done-do-not-repeat).

## Local stack

```bash
docker compose -f docker/docker-compose.yml --profile dev up --build
```

For day-to-day development use `pixi run dev` / `pixi run frontend`. See the
README and `docs/adr/0005-local-dev-stack-compose.md`.
