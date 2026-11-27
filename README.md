# CivicPulse — AI-Based Civic Issue Monitoring System

A production-grade platform for reporting, classifying, and resolving civic issues
(potholes, garbage, debris) for the Vadodara Municipal Corporation. Citizens
submit geo-tagged photos; a computer-vision model classifies them; LangGraph
agents route, escalate, and assign work to engineers; a Next.js dashboard tracks
resolution end-to-end. Scheduled drift detection keeps the model honest.

![CI](https://github.com/BORUTOUZUMAKI07/ai-civic-issue-monitoring/actions/workflows/ci.yml/badge.svg)

## Table of contents

- [Architecture](#architecture)
- [Request lifecycle](#request-lifecycle)
- [Data model](#data-model)
- [Authentication flow](#authentication-flow)
- [ML pipeline](#ml-pipeline)
- [Observability](#observability)
- [Deployment](#deployment)
- [Setup](#setup)
- [Commands](#commands)

## Architecture

```mermaid
flowchart TB
    subgraph Client["Browser"]
        FE[Next.js 16 App Router]
        Proxy["/api/proxy (BFF)"]
    end

    subgraph Backend["FastAPI Backend"]
        API[REST API + Middleware]
        Auth[Auth Domain]
        Issues[Issues Domain]
        ML[ML Inference]
        Agents[LangGraph Agents]
        RAG[RAG Retrieval]
    end

    subgraph Data["Datastores"]
        PG[(PostgreSQL)]
        Redis[(Redis / Upstash)]
        Mongo[(MongoDB)]
    end

    subgraph Ops["Operations"]
        Prefect[Prefect Cloud]
        OTEL[OTel Collector - local Compose / free Render service]
        NR[New Relic]
    end

    FE --> Proxy
    Proxy --> API
    API --> Auth
    API --> Issues
    Issues --> ML
    Issues --> Agents
    Agents --> RAG
    API --> PG
    API --> Redis
    API --> Mongo
    ML --> Mongo
    Prefect --> PG
    Prefect --> Mongo
    API -->|OTLP/HTTP + Basic auth| OTEL
    OTEL -->|vendor-aware exporter| NR
```

### Component responsibilities

| Layer | Component | Responsibility |
| ----- | --------- | -------------- |
| Frontend | Next.js App Router | Dashboard, map, admin/review, issue reporting |
| Frontend | BFF proxy (`/api/proxy`) | Auth cookie scoping, path allowlist, body limits |
| Backend | FastAPI + middleware | RBAC, rate limiting, request logging, metrics |
| Backend | Auth domain | JWT access/refresh, TOTP 2FA, OAuth, sessions |
| Backend | Issues domain | Upload, gate, classify, assign, resolve, idempotency |
| Backend | ML inference | MobileNetV2 (PyTorch/ONNX), drift logging |
| Backend | LangGraph agents | Classify, route, match, escalate, analytics |
| Backend | RAG | Vector + BM25 hybrid retrieval over issue history |
| Data | PostgreSQL | Users, issues, wards, engineers, assignments |
| Data | Redis | Rate limits, cache, token blacklist, sessions |
| Data | MongoDB | Audit logs, drift reports, rejected uploads |
| Ops | Prefect | Drift, SLA, reporting, retraining flows |
| Ops | OTel collector (local Compose / free Render) | Receives all three OTLP signals, owns the vendor key, queues to disk, optional Grafana overlay |

## Request lifecycle

```mermaid
sequenceDiagram
    participant U as User
    participant FE as Next.js
    participant BFF as /api/proxy
    participant API as FastAPI
    participant MW as Middleware
    participant SVC as Issue Service
    participant ML as ML Inference
    participant DB as PostgreSQL

    U->>FE: Submit photo + location
    FE->>BFF: POST /api/proxy/issues (Idempotency-Key)
    BFF->>API: Forward (auth cookie -> Bearer)
    API->>MW: RBAC + rate limit + body limit
    MW->>SVC: create_issue
    SVC->>ML: predict_issue(image)
    ML-->>SVC: label, confidence, probabilities
    SVC->>SVC: gate_decision(vision, description)
    SVC->>DB: INSERT issue (ward geofence)
    SVC-->>API: IssueResponse
    API-->>BFF: JSON
    BFF-->>FE: JSON (Set-Cookie rewritten)
    FE-->>U: Show issue card + toast
```

## Data model

```mermaid
erDiagram
    User ||--o{ Issue : reports
    User ||--o| Engineer : "has profile"
    Ward ||--o{ Issue : contains
    Ward ||--o{ Engineer : "assigned to"
    Issue ||--o{ Assignment : has
    Issue ||--o| Resolution : resolved_by
    Engineer ||--o{ Assignment : receives
    Issue }o--|| IdempotencyKey : "upload replay"

    User {
        int id
        string email
        string role
        bool is_active
        bool two_factor_enabled
    }
    Issue {
        int id
        enum type
        float confidence
        enum status
        float latitude
        float longitude
        int ward_id
        int reporter_id
    }
    Ward {
        int id
        string name
        jsonb polygon
    }
    Engineer {
        int id
        int user_id
        int ward_id
        string specialization
        int current_workload
    }
```

## Authentication flow

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI
    participant Redis as Redis

    C->>API: POST /auth/login (email, password)
    API->>API: verify password (Argon2)
    alt 2FA enabled
        API-->>C: 2fa_challenge token
        C->>API: POST /auth/2fa/verify (challenge, code)
    end
    API->>Redis: store refresh session (sid, fam)
    API-->>C: Set-Cookie access_token, refresh_token, session_active

    Note over C,API: Access token expires (15 min)
    C->>API: POST /auth/refresh (cookie)
    API->>Redis: rotate refresh token (new sid, same fam)
    API-->>C: new access + refresh cookies

    C->>API: POST /auth/logout
    API->>Redis: revoke session family
    API-->>C: clear cookies
```

## ML pipeline

```mermaid
flowchart LR
    A[Image Upload] --> B[Gate: vision + text]
    B -->|accept| C[MobileNetV2 Inference]
    B -->|reject| D[Rejected Upload Log]
    B -->|review_required| E[Admin Review Queue]
    C --> F[Label + Confidence + Probs]
    F --> G[Issue Created]
    G --> H[Embedding Generated]
    H --> I[RAG Context for Agents]
    I --> J[LangGraph agent pipeline]

    K[Prefect: Drift Detection] --> L[MongoDB predictions]
    L --> K
    K -->|drift high| M[Retrain Flow]
    M --> N[MLflow / DagsHub]
    N --> O[New model artifact]
```

### Agent graph

```mermaid
flowchart TD
    A[Input issue] --> B[classify_issue]
    B --> C[route_issue]
    C --> D{needs escalation}
    D -->|yes| E[escalate_issue]
    D -->|analytics| F[generate_analytics]
    D -->|no| G[match_engineer]
    E --> H[END]
    F --> H
    G --> H
```

## Observability

```mermaid
flowchart LR
    App[FastAPI App] -->|OTLP/HTTP + Basic auth| Collector[OTel Collector: local or Render]
    Collector -->|vendor-aware exporter| NR[New Relic]
    Collector -->|opt-in overlay| Grafana[Grafana]
    App -->|structured JSON logs| stdout
```

In production all three signals (logs, metrics and traces) go to a dedicated
free Render collector at `https://civicpulse-otel-collector.onrender.com`. The
backend holds only the OTLP endpoint and a Basic-auth pair; the collector alone
holds `NEW_RELIC_LICENSE_KEY`, so no vendor key reaches the backend or browser.
Free Render services sleep after 15 minutes idle, so telemetry emitted while the
collector wakes can be dropped. That is the accepted trade-off: export is
fail-open, and `/health/telemetry` is a diagnostic snapshot, not a traffic gate.

Local Docker Compose runs the same collector config with `PORT=4318`, a
disk-backed queue and an opt-in Grafana overlay. There is no Prometheus scrape
path and no scraper to deploy. Browser errors travel
`browser → /api/client-errors (Next route) → backend structured logs → OTLP`,
so no vendor key reaches the browser. See
[ADR-0010](docs/adr/0010-render-collector-topology.md) (which supersedes
[ADR-0009](docs/adr/0009-direct-otlp-ingest.md)) and
[`docs/new-relic-alerts.md`](docs/new-relic-alerts.md).

## Deployment

```mermaid
flowchart TB
    Dev[Developer] -->|push main| GH[GitHub]
    GH -->|green CI| Deploy[CI-gated Deploy workflow]
    Deploy -->|Deploy Hook| Collector[Render: OTel collector]
    Deploy -->|Deploy Hook| Backend[Render: FastAPI]
    Deploy -->|Deploy Hook| Frontend[Vercel: Next.js BFF]
```

## Setup

### Prerequisites

- [Pixi](https://pixi.sh) (conda-forge)
- Node.js 22 LTS + npm
- Docker + Docker Compose (optional)

### Install

```bash
git clone https://github.com/BORUTOUZUMAKI07/ai-civic-issue-monitoring.git
cd ai-civic-issue-monitoring

# `git clone` calls this remote `origin`; the canonical code remote is `github`.
# In this project `origin` is reserved for the DagsHub ML/DVC artifact mirror.
git remote rename origin github
# Optional: restore the DagsHub ML/DVC mirror under this project's `origin` convention.
# git remote add origin https://dagshub.com/ram.atchutratna/ai-civic-issue-monitoring.git
git remote -v   # github -> GitHub (code); origin -> DagsHub (ML/DVC), if added
# Never `git push origin` for app code — that remote is the ML artifact mirror.

pixi install
cd frontend && npm install && cd ..

cp backend/.env.example backend/.env
# edit backend/.env: SECRET_KEY, DATABASE_URL, REDIS_URL, MONGODB_URI

pixi run setup
```

### First admin (fresh local database only)

```bash
ADMIN_EMAIL=you@example.com ADMIN_PASSWORD='<12+ chars>' ADMIN_ROLE=super_admin pixi run create-admin
```

This is a one-time bootstrap for an empty local database. **Do not rerun it on
the hosted production database** — exactly one `super_admin` is enforced by
migration `012`, and further admins must be created through the admin API.

### Run

```bash
pixi run dev            # backend :8000
pixi run frontend       # frontend :3000
```

Or full stack:

```bash
cp docker/.env.example docker/.env   # set SECRET_KEY
docker compose -f docker/docker-compose.yml --profile dev up --build
```

## Commands

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
dvc pull
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
- Drift detection via Prefect
- SLA monitoring and daily reports
- Dedicated Render OTLP collector in production and local Compose; no vendor key in the app

## Tech stack

Backend: FastAPI, SQLAlchemy 2.0 (async), PostgreSQL, Beanie + MongoDB,
Redis/Upstash, LangGraph, PyTorch + MobileNetV2, PyJWT.

Frontend: Next.js 16, React 19, Tailwind CSS v4, shadcn/ui (Radix), TanStack
Query, Leaflet, Recharts.

DevOps: Pixi, Docker Compose, Prefect Cloud, GitHub Actions, OpenTelemetry.

## Documentation

- [`docs/production-deployment.md`](docs/production-deployment.md) — production deployment runbook
- [`docs/deployment.md`](docs/deployment.md) — release artifacts, remotes, and local stack
- [`docs/adr/`](docs/adr/) — architecture decision records
