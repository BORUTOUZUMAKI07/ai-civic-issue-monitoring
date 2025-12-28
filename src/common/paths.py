from pathlib import Path

# Project root (ai-civic-issue-monitoring/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Data paths
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"

# Model paths
MODELS_DIR = PROJECT_ROOT / "models"
BEST_MODEL_PATH = MODELS_DIR / "model_phase1.pth"

# Config paths
CONFIGS_DIR = PROJECT_ROOT / "configs"

# Logs
LOGS_DIR = PROJECT_ROOT / "logs"

def ensure_dirs():
    """Ensure all required directories exist."""
    DIRS = [DATA_DIR, RAW_DATA_DIR, PROCESSED_DATA_DIR, MODELS_DIR, LOGS_DIR]
    for d in DIRS:
        d.mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    print(f"Project Root: {PROJECT_ROOT}")
    ensure_dirs()
