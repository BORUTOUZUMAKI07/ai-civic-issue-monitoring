# AI-Based Civic Issue Monitoring System

A professional, production-grade system for monitoring and managing civic issues for the Vadodara Municipal Corporation.

# 🚀 Setup & Installation

This project uses **Mamba** for environment management and **uv** for high-speed dependency resolution.

### 1. Prerequisites
-   [Mamba](https://github.com/conda-forge/miniforge#mambaforge) (Recommended) or Conda
-   git

> **Tip**: If you have Conda but not Mamba, install it: `conda install -n base -c conda-forge mamba`
> 
> **Note**: This setup supports both **CPU** and **GPU** automatically. The installed PyTorch version includes necessary CUDA binaries.

### 2. Create the Base Environment
Create a clean environment with Python and uv:
```bash
# Option 1: Using Mamba (Faster)
mamba env create -f environment.yaml

# Option 2: Using Conda (If Mamba is missing)
conda env create -f environment.yaml

# Activate the environment
conda activate civic-ai
```
*Note: If `mamba` is not available, you can use `conda env create -f environment.yaml`.*

### 3. Install Dependencies
Initialize the project environment and install dependencies using uv:
```bash
# Create a virtual environment in .venv
uv venv

# Install dependencies from pyproject.toml
uv sync
```

### 4. Running commands
Run commands using the virtual environment (ensure PYTHONPATH includes src):
```bash
# Run tests
uv run pytest

# Run the API
uv run uvicorn app.main:app --reload

# Run training
uv run python src/ml/training/train.py
```

## 🏗️ Project Structure
- `src/app/`: FastAPI Backend.
- `src/ml/`: ML Pipeline (Training, Evaluation, Inference).
- `src/common/`: Shared utilities and paths.
- `frontend/`: Mobile-First PWA (Vite + React).
- `docker/`: Containerization and monitoring stack.
- `configs/`: Hydra configurations.
- `data/`: DVC-tracked data directories.
- `models/`: DVC-tracked model weights.