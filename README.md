# CivicPulse — AI-Based Civic Issue Monitoring System

A production-grade platform for reporting, classifying, and resolving civic issues
(potholes, garbage, debris) for the Vadodara Municipal Corporation. Citizens
submit geo-tagged photos; a computer-vision model classifies them; LangGraph
agents route, escalate, and assign work to engineers; a Next.js dashboard tracks
resolution end-to-end. Scheduled drift detection keeps the model honest.

![CI](https://github.com/BORUTOUZUMAKI07/ai-civic-issue-monitoring/actions/workflows/ci.yml/badge.svg)

## Architecture

| Component      | Technology                          | Purpose |
| -------------- | ----------------------------------- | ------- |
| Backend        | FastAPI (async)                     | REST API, auth, issue lifecycle, ML inference |
| Frontend       | Next.js 16 (App Router)             | Dashboard, map, admin/review UI |
| ML Engine      | PyTorch (MobileNetV2) + LangGraph   | Image classification + agent pipeline |
| Monitoring     | Prefect + statistical drift checks  | Confidence/label drift detection |
| Orchestration  | Prefect Cloud                       | Drift, SLA, reporting, retraining flows |
| Observability  | OpenTelemetry (OTLP -> collector)   | Logs, traces, RED metrics |
| Datastores     | PostgreSQL, Redis/Upstash, MongoDB  | Issues/users, cache/rate-limit, audit/drift |
| Packaging      | Pixi (conda-forge)                  | Python + native C/C++ deps in one env |
| Container      | Docker Compose                      | Full-stack orchestration |

## Repository layout

```
backend/        FastAPI app, domains, core, agents, ML, tests, migrations
frontend/       Next.js app (App Router), components, tests, e2e
prefect/        Prefect flows and deployment config
docker/         Compose stack + OpenTelemetry collector config
docs/           Deployment guide and ADRs
backend/data/   Seed data and evaluation goldens
```

## Prerequisites

- [Pixi](https://pixi.sh) (conda-forge) — manages Python and native C/C++ libs
- Node.js 22 LTS + npm
- Docker + Docker Compose (optional, for the full stack)
- PostgreSQL 16, Redis, MongoDB (or use the `dev` Compose profile)

## Setup

```bash
git clone https://github.com/BORUTOUZUMAKI07/ai-civic-issue-monitoring.git
cd ai-civic-issue-monitoring

pixi install
cd frontend && npm install && cd ..

cp backend/.env.example backend/.env
# edit backend/.env: SECRET_KEY, DATABASE_URL, REDIS_URL, MONGODB_URI, ...

pixi run setup          # pre-commit hooks
```

Two additional env files are scoped to their own component:
`prefect/.env.example -> prefect/.env` and `docker/.env.example -> docker/.env`.

### First admin account

The public API only registers `field_worker`/`viewer`. Create the first
`super_admin` directly against the database:

```bash
ADMIN_EMAIL=you@example.com ADMIN_PASSWORD='<12+ chars>' ADMIN_ROLE=super_admin pixi run create-admin
```

Idempotent — re-running promotes/updates the existing account.

## Running

Local development:

```bash
pixi run dev            # backend on :8000
pixi run frontend       # frontend on :3000
```

Full stack with Docker:

```bash
cp docker/.env.example docker/.env   # set SECRET_KEY
docker compose -f docker/docker-compose.yml --profile dev up --build
```

Access:

| Service            | URL                          |
| ------------------ | ---------------------------- |
| Frontend dashboard | http://localhost:3000        |
| Backend API docs   | http://localhost:8000/docs   |

## Development commands

Backend:

```bash
pixi run dev            # hot-reload server
pixi run test           # tests
pixi run test-ci        # tests (skip integration)
pixi run lint           # ruff
pixi run lint-fix       # ruff auto-fix
pixi run typecheck      # mypy
pixi run format         # ruff format
pixi run migrate        # alembic upgrade head
pixi run migrate-create # new migration
pixi run seed           # seed wards
pixi run train          # train ML model
pixi run create-admin   # bootstrap first admin
```

Frontend:

```bash
pixi run frontend       # dev server
pixi run frontend-build # production build
pixi run frontend-test  # vitest
```

Data (DVC):

```bash
dvc pull                # training data + model artifacts
dvc add models/model.onnx && dvc push
```

## Features

- Real-time classification: MobileNetV2 image classifier with keyword fallback
- Agent pipeline: LangGraph routing, escalation, engineer matching
- Intake gate: vision + description three-way accept/reject/review
- Ward geofencing: point-in-polygon assignment
- Idempotent uploads with `Idempotency-Key`
- Refresh-token rotation with family revocation
- TOTP two-factor auth with recovery codes
- OAuth (Google, GitHub)
- RBAC: super_admin / admin / engineer / field_worker / viewer
- Real-time issue stream over WebSocket
- Admin review queue, user management, engineer roster
- Dashboard stats, heatmap, public aggregate stats
- Drift detection (confidence/label distribution) via Prefect
- SLA monitoring and daily reports
- OTLP observability to a Layer-2 collector

## Prefect flows

| Flow              | Schedule        | Purpose |
| ----------------- | --------------- | ------- |
| drift-detection   | Daily 2 AM UTC  | Model accuracy/distribution drift |
| sla-monitoring    | Hourly          | Issue resolution SLA compliance |
| daily-report      | Daily 8 AM UTC  | Daily issue summary |
| audit-log-archival| Monthly         | Archive old audit logs |
| retrain-model     | Weekly + event  | Drift-triggered retraining via MLflow/DagsHub |

## Tech stack

Backend: FastAPI, SQLAlchemy 2.0 (async), PostgreSQL, Beanie + MongoDB,
Redis/Upstash, LangGraph, PyTorch + MobileNetV2, PyJWT.

Frontend: Next.js 16, React 19, Tailwind CSS v4, shadcn/ui (Radix), TanStack
Query, Leaflet, Recharts.

DevOps: Pixi, Docker Compose, Prefect Cloud, GitHub Actions, OpenTelemetry.

## CI/CD

CI builds, tests, scans, and publishes container images. Publishing to
DockerHub and the manual Deploy workflow are opt-in. See
[`docs/deployment.md`](docs/deployment.md).

## Documentation

- [`docs/deployment.md`](docs/deployment.md) — deployment runbook
- [`docs/ddd-backend-refactor-plan.md`](docs/ddd-backend-refactor-plan.md) — backend refactor plan
- [`docs/adr/`](docs/adr/) — architecture decision records
