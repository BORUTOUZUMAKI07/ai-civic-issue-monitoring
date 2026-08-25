# AI-Based Civic Issue Monitoring System

A professional, production-grade system for monitoring and managing civic issues for the Vadodara Municipal Corporation.

![CI Status](https://github.com/ram.atchutratna/ai-civic-issue-monitoring/actions/workflows/ci.yml/badge.svg)
 This system uses Computer Vision to classify issues (potholes, garbage, etc.) and Real-Time Drift Detection to ensure model reliability.

---

## Project Architecture

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Backend** | FastAPI | High-performance API for issue uploads and inference. |
| **Frontend** | Next.js | Clean, responsive dashboard for viewing issues. |
| **ML Engine** | PyTorch + LangGraph | Custom trained models for issue classification + agent pipeline. |
| **Monitoring** | Prefect + statistical drift checks | Scheduled confidence/label drift detection on logged predictions. |
| **Scheduling** | Prefect Cloud | Automated drift detection, SLA monitoring, reporting, and ML retraining. |
| **Observability** | NewRelic | APM and distributed tracing. |
| **Containerization** | Docker | Full stack orchestration via Docker Compose. |

**Directory Structure:**
- `backend/src/`: FastAPI backend (domains, models, repositories, agents).
- `backend/ml/`: ML Pipeline (training, evaluation, drift detection).
- `prefect/`: Prefect Cloud flows and deployment config.
- `frontend/`: Next.js application.
- `docker/`: Dockerfiles and Compose configurations.

---

## Why Pixi?

This project uses **[Pixi](https://pixi.sh)** (conda-forge) instead of UV or Pip because it depends on **native C/C++ libraries** that pure Python package managers cannot install:

| Dependency | System Library Needed | Why |
| :--- | :--- | :--- |
| **PyTorch** | `libgomp`, `libstdc++` | C++ runtime for tensor operations |
| **OpenCV** | `libgl1`, `libglib2.0-0` | GUI and image processing backends |
| **asyncpg** | `libpq-dev` | PostgreSQL C client library |
| **MongoDB (motor)** | `libssl` | TLS for database connections |
| **Argon2** | `libffi-dev` | Password hashing C extension |
| **pgvector** | `postgresql-devel` | Vector search extension headers |

UV and Pip only manage **Python packages** — they cannot install system-level C libraries. This forces you into a messy hybrid of `apt-get install` + `pip install` + manual `LD_LIBRARY_PATH` hacks. **Pixi resolves both Python and native dependencies in a single, reproducible environment** via conda-forge channels.

## Setup & Installation

### 1. Prerequisites

Install Pixi (one-time setup):

```bash
# macOS / Linux
curl -fsSL https://pixi.sh/install.sh | bash

# Windows (PowerShell)
powershell -c "irm https://pixi.sh/install.ps1 | iex"
```

### 2. Environment Setup

```bash
# Clone the repository
git clone https://github.com/ram.atchutratna/ai-civic-issue-monitoring.git
cd ai-civic-issue-monitoring

# Install all dependencies (Python + native C libs + frontend)
# This single command handles: PyTorch, OpenCV, PostgreSQL driver, MongoDB driver,
# FastAPI, LangGraph, and all system libraries they need
pixi install

# Install frontend dependencies (npm)
cd frontend && npm install && cd ..

# Set up pre-commit hooks
pixi run setup
```

The `pixi.toml` declares:
- **`channels = ["conda-forge", "pytorch"]`** — pulls native C libraries from conda-forge and PyTorch from the official channel
- **`[pypi-dependencies]`** — pulls Python packages from PyPI (FastAPI, SQLAlchemy, LangGraph, etc.)
- **PyTorch `index-url = "https://download.pytorch.org/whl/cpu"`** — CPU-only builds to keep the image small

### 3. Environment Variables

Copy the example env file and fill in your values:

```bash
cp .env.example .env
```

---

## Running the Application

### Local Development

```bash
# Start backend (in one terminal)
pixi run dev

# Start frontend (in another terminal)
pixi run frontend
```

### With Docker Compose

```bash
docker-compose up -d --build
```

### Accessing Services

| Service | URL | Credentials |
| :--- | :--- | :--- |
| **Frontend Dashboard** | [http://localhost:3000](http://localhost:3000) | - |
| **Backend API Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) | - |

---

## Development Commands

### Backend

```bash
# Run backend with hot reload
pixi run dev

# Run tests
pixi run test

# Run tests (CI mode, skip integration)
pixi run test-ci

# Lint code
pixi run lint

# Auto-fix lint issues
pixi run lint-fix

# Type check
pixi run typecheck

# Format code
pixi run format

# Run database migrations
pixi run migrate

# Create new migration
pixi run migrate-create

# Seed ward data
pixi run seed

# Train ML model
pixi run train
```

### Frontend

```bash
# Run frontend dev server
pixi run frontend

# Build for production
pixi run frontend-build

# Run frontend tests
pixi run frontend-test
```

### DVC (Data Version Control)

```bash
# Pull training data + model artifacts (versioned, not stored in git)
dvc pull

# Version a model artifact after retraining
dvc add models/model.onnx
dvc push
```

---

## Monitoring & Drift Detection

We use scheduled **drift detection** (confidence/label distribution vs. baseline) and **LangGraph** agents to ensure the model doesn't "drift" (i.e., perform poorly on new, unseen data).

### Key Features

1. **Real-Time Classification**: MobileNetV2 + keyword-based fallback classifier
2. **Agent Pipeline**: LangGraph-based routing, escalation, and matching
3. **Drift Detection**: Automated accuracy and distribution drift monitoring via Prefect
4. **SLA Monitoring**: Hourly checks for issue resolution compliance

### Prefect Flows

| Flow | Schedule | Purpose |
| :--- | :--- | :--- |
| `drift-detection` | Daily 2AM UTC | Check for model accuracy/distribution drift |
| `sla-monitoring` | Hourly | Monitor issue resolution SLA compliance |
| `daily-report` | Daily 8AM UTC | Generate daily issue summary reports |
| `audit-log-archival` | Monthly | Archive old audit logs to cold storage |
| `retrain-model` | Weekly + event-driven | Drift-triggered ML retraining via MLflow (DagsHub) |

---

## Tech Stack

### Backend
- FastAPI + Uvicorn
- SQLAlchemy 2.0 (async) + PostgreSQL + pgvector
- Beanie + MongoDB (audit logs, drift reports)
- Redis + Upstash (rate limiting, caching, token blacklist)
- LangGraph (agent pipeline)
- PyTorch + MobileNetV2 (image classification)

### Frontend
- Next.js 16 + React 19 (App Router, `output: "standalone"`)
- Tailwind CSS v4 + shadcn/ui (Radix primitives) + Aceternity/Magic UI accents
- Geist font + lucide-react icons
- TanStack React Query (server state)
- Leaflet (maps) + Recharts (charts) + Motion (animations)

### DevOps
- Pixi (Python package management)
- Docker + Docker Compose
- Prefect Cloud (scheduling + orchestration)
- GitHub Actions (CI/CD)
- NewRelic (observability)
