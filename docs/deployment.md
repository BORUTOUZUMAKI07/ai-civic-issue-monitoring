# Deployment & Release

CI builds and publishes; it deliberately does **not** ship anything to a host
on its own. This page lists what each workflow produces, and how to turn on the
two opt-in pieces: DockerHub publishing and the deploy workflow.

Both are inert until you configure them — a fresh clone runs neither.

## What CI publishes

| Trigger | Workflow / job | Artifact | Condition |
| :--- | :--- | :--- | :--- |
| push to `main` | `ci.yml` → **Docker → GHCR** | `ghcr.io/<owner>/<repo>/backend:<sha>` and `:latest`, `ghcr.io/<owner>/<repo>/frontend:<sha>` and `:latest` | always |
| tag `v*.*.*` | `ci.yml` → **Docker → DockerHub** | `<dockerhub-user>/civic-backend[:<tag>]`, `<dockerhub-user>/civic-frontend[:<tag>]` | only if both DockerHub secrets exist |

`<owner>/<repo>` is lower-cased before it is used as an image name
(GHCR requires lowercase repositories).

## Opt in: publishing to DockerHub

1. Create a DockerHub **access token** with *Write* scope.
2. In the repository: **Settings → Secrets and variables → Actions → Secrets**
   and add
   - `DOCKERHUB_USERNAME`
   - `DOCKERHUB_TOKEN`
3. Push a release tag:

   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

Without those secrets the **Docker → DockerHub** job still runs on a tag, but
every publish step is skipped and the job goes green with a
`DockerHub publish skipped` notice. That is intentional: a job-level `if:`
cannot read the `secrets` context, so the credential probe has to happen in the
first step (it is id — `creds`), and each publish step is conditioned on
`steps.creds.outputs.enabled == 'true'`. Previously the job hard-failed every
tagged release when the secrets were absent.

## Opt in: the Deploy workflow

`.github/workflows/deploy.yml` is a **manual-only, disabled-by-default**
template. It never runs from a normal push.

### 1. Enable it

**Settings → Secrets and variables → Actions → Variables**

| Name | Value |
| :--- | :--- |
| `DEPLOY_ENABLED` | `true` |

Until that variable exists, every run resolves `enabled=false`, prints a
`Deploy disabled` notice and finishes green without touching anything.

### 2. Configure the target (secrets)

| Secret | Meaning |
| :--- | :--- |
| `DEPLOY_HOST` | Public hostname or IP of the machine |
| `DEPLOY_USER` | SSH user |
| `DEPLOY_SSH_KEY` | Private key (PEM) authorised for that user |
| `DEPLOY_PATH` | Path to **this repository's checkout** on that machine |

The target must have:

- a git checkout of this repository at `DEPLOY_PATH` whose `origin` is this
  repo (the workflow `git fetch`es and detaches onto the requested ref),
- Docker Engine with the Compose **v2 plugin**,
- `docker/.env` created from `docker/.env.example` with a real `SECRET_KEY`
  plus the production `DATABASE_URL` / `REDIS_URL` / `MONGODB_URI`
  (see `docs/adr/0005` — compose refuses to boot without `SECRET_KEY`),
- `curl` available (used for the health check).

### 3. Run it

**Actions → Deploy → Run workflow**, choosing:

- `environment` — `staging` or `production` (used for the concurrency group),
- `ref` — a tag or commit SHA to deploy; leave empty to deploy the current
  HEAD of the branch you dispatched from.

A run then does, over SSH:

```bash
git fetch --prune origin
git checkout --detach <ref>
docker compose -f docker/docker-compose.yml build
docker compose -f docker/docker-compose.yml run --rm backend python -m alembic upgrade head
docker compose -f docker/docker-compose.yml up -d
# poll http://localhost:8000/health for up to 60s, print backend logs on failure
```

The migration runs against the freshly built image *before* the stack is
recreated, and a run that never reaches a healthy `/health` exits non-zero.

### Optional extras

- **Manual approval gates:** create GitHub *Environments* named `staging` /
  `production` with required reviewers, then uncomment the
  `environment: ${{ needs.resolve.outputs.environment }}` line in
  `deploy.yml`.
- **Auto-CD:** uncomment the `push: branches: [main]` block in `deploy.yml` so
  every push to `main` deploys itself (the `DEPLOY_ENABLED` gate still applies).

## What CI/CD does *not* do: seed data

Ward seeding is a one-off against the target database and the backend image
does not ship `backend/scripts/`:

```bash
pixi run seed        # runs scripts/seed_wards.py locally
```

## Alternative targets (image-based deploys)

`docker/docker-compose.yml` builds from source (ADR-0005), which is what the
deploy template above uses. For platforms that deploy from a registry instead
— Render, Fly.io, Kubernetes, or `docker run` on a VM — pull the images CI
already pushed:

```text
ghcr.io/<owner>/<repo>/backend:<sha>
ghcr.io/<owner>/<repo>/frontend:<sha>
```

The backend image is self-contained (`uvicorn src.main:app` on port 8000 with a
`/health` Docker HEALTHCHECK) and still contains `alembic/` + `alembic.ini`, so
the migration command stays `python -m alembic upgrade head`.

## Local stack

Unchanged: `docker compose -f docker/docker-compose.yml --profile dev up --build`
for the full local stack, or `pixi run dev` / `pixi run frontend` for day-to-day
development. See the README and `docs/adr/0005-local-dev-stack-compose.md`.
