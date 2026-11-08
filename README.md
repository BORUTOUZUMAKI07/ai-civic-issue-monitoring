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
        OTEL[OTel Collector]
        NR[New Relic / Grafana]
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
    API --> OTEL
    OTEL --> NR
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
| Ops | OTel collector | Fan-out to New Relic / Grafana |

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
    App[FastAPI App] -->|OTLP logs/traces/metrics| Collector[OTel Collector]
    Collector -->|basic auth| NR[New Relic]
    Collector -->|config flag| Grafana[Grafana]
    App -->|structured JSON logs| stdout
```

Three layers: app instruments (FastAPI, httpx, SQLAlchemy, HTTP middleware) export over OTLP to a Layer-2 collector that owns the vendor key and fans out to any OTLP sink. No Prometheus scrape path.

## Deployment

```mermaid
flowchart TB
    Dev[Developer] -->|push| GH[GitHub]
    GH -->|CI| Lint[Lint + Typecheck]
    Lint --> Tests[Tests + Integration]
    Tests --> Build[Docker Build]
    Build --> GHCR[GHCR Registry]
    GHCR -->|opt-in tag| DH[DockerHub]
    GHCR -->|manual deploy| Host[Production Host]
    Host --> Compose[Docker Compose]
    Compose --> Backend[Backend Container]
    Compose --> Frontend[Frontend Container]
    Compose --> Collector[OTel Collector]
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

pixi install
cd frontend && npm install && cd ..

cp backend/.env.example backend/.env
# edit backend/.env: SECRET_KEY, DATABASE_URL, REDIS_URL, MONGODB_URI

pixi run setup
```

### First admin

```bash
ADMIN_EMAIL=you@example.com ADMIN_PASSWORD='<12+ chars>' ADMIN_ROLE=super_admin pixi run create-admin
```

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
- OTLP observability to a Layer-2 collector

## Tech stack

Backend: FastAPI, SQLAlchemy 2.0 (async), PostgreSQL, Beanie + MongoDB,
Redis/Upstash, LangGraph, PyTorch + MobileNetV2, PyJWT.

Frontend: Next.js 16, React 19, Tailwind CSS v4, shadcn/ui (Radix), TanStack
Query, Leaflet, Recharts.

DevOps: Pixi, Docker Compose, Prefect Cloud, GitHub Actions, OpenTelemetry.

## Documentation

- [`docs/deployment.md`](docs/deployment.md) — deployment runbook
- [`docs/adr/`](docs/adr/) — architecture decision records
