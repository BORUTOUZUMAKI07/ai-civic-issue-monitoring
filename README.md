# AI-Based Civic Issue Monitoring System

A professional, production-grade system for monitoring and managing civic issues for the Vadodara Municipal Corporation.

![CI Status](https://github.com/ram.atchutratna/ai-civic-issue-monitoring/actions/workflows/ci.yml/badge.svg)
 This system uses Computer Vision to classify issues (potholes, garbage, etc.) and Real-Time Drift Detection to ensure model reliability.

---

## 🏗️ Project Architecture

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Backend** | FastAPI | High-performance API for issue uploads and inference. |
| **Frontend** | React + Vite | Clean, responsive dashboard for viewing issues. |
| **ML Engine** | PyTorch + Hydra | Custom trained models for issue classification. |
| **Monitoring** | Alibi Detect | **Real-Time** data drift detection (K-S Test & Chi-Square). |
| **Observability** | Prometheus + Grafana | Metrics collection and visualization dashboards. |
| **Containerization** | Docker | Full stack orchestration via Docker Compose. |

**Directory Structure:**
- `src/app/`: FastAPI Backend & Services.
- `src/ml/`: ML Pipeline (Training, Evaluation, Drift Detection).
- `frontend/`: React Application.
- `docker/`: Dockerfiles and Compose configurations.
- `configs/`: Hyperparameter configurations (Hydra).

---

## 🚀 Setup & Installation

This project uses a hybrid **Mamba + UV** workflow for maximum speed and stability.

### 1. Prerequisites
- [Mamba](https://github.com/conda-forge/miniforge#mambaforge) (Recommended) or Conda
- Docker & Docker Compose

### 2. Environment Setup
Create the base environment and sync dependencies:

```bash
# 1. Create Base Environment (System Dependencies)
mamba env create -f environment.yaml

# 2. Activate
mamba activate civic-ai

# 3. Install Python Dependencies (Project Libraries)
uv sync --extra research
```

---

## 🏃 Running the Application

The entire stack runs in Docker.

```bash
# Start all services (Backend, Frontend, Prometheus, Grafana)
docker-compose up -d --build
```

### Accessing Services

| Service | URL | Credentials |
| :--- | :--- | :--- |
| **Frontend Dashboard** | [http://localhost:5173](http://localhost:5173) | - |
| **Backend API Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) | - |
| **Grafana** | [http://localhost:3001](http://localhost:3001) | User: `admin`, Pass: `admin` |
| **Prometheus** | [http://localhost:9090](http://localhost:9090) | - |

---

## 📊 Monitoring & Drift Detection

We use **Alibi Detect** to ensure the model doesn't "drift" (i.e., perform poorly on new, unseen data).

### Key Metrics (in Grafana)

| Metric Name | Meaning | Alert Condition |
| :--- | :--- | :--- |
| `model_drift_detected_confidence` | **1** = Drift Detected, **0** = Normal | **Value = 1** |
| `model_drift_p_value_confidence` | Statistical similarity score (K-S Test) | **Value < 0.05** |

### How it Works
1.  **Online Buffering**: The backend buffers the last **5 uploads** (Configurable).
2.  **Real-Time Check**: Once the buffer fills, it runs Alibi Detect's K-S Test.
3.  **Alerting**: If drift is found, the Prometheus metric is set to `1`.

---

## 💻 Development Commands

Running scripts locally (outside Docker) using `uv run`:

```bash
# 1. Run Tests
uv run pytest

# 2. Run Backend Locally
uv run uvicorn app.main:app --reload

# 3. Train the Model
uv run python src/ml/training/train.py

# 4. Run Standalone Drift Demo
$env:PYTHONPATH = "$env:PYTHONPATH;$PWD\src"; uv run src/ml/monitoring/drift_detection.py
```