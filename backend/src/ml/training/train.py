"""Training pipeline for CivicPulse issue classifier.

Uses MobileNetV2 with LoRA/DoRA PEFT adapters.
Hyperparameter search via Optuna with persistent storage.
Experiment tracking via DagsHub MLflow.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import mlflow
import mlflow.pytorch
import optuna
import torch
import torch.nn as nn
import torch.optim as optim
import yaml
from torch.utils.data import DataLoader
from torchvision import datasets, transforms

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
NUM_CLASSES = 4
CLASS_NAMES = ["debris", "garbage", "non_civic", "pothole"]
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

MLFLOW_TRACKING_URI = os.getenv(
    "MLFLOW_TRACKING_URI",
    "https://dagshub.com/ram.atchutratna/ai-civic-issue-monitoring.mlflow",
)
DATA_PATH = os.getenv("DATA_PATH", "data/raw")
CONFIG_PATH = Path(__file__).resolve().parent.parent.parent.parent / "configs" / "mlflow.yaml"
ADAPTER_DIR = Path("models/adapter")
METRICS_PATH = Path("metrics/train.json")


def load_config() -> dict:
    """Load training config from YAML."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f)
    return {}


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def get_dataloaders(data_path: str, batch_size: int) -> tuple[DataLoader, DataLoader, list[str]]:
    """Load train/val data from data/raw directory."""
    train_dir = Path(data_path) / "train"
    val_dir = Path(data_path) / "val"

    train_transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(15),
        transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    val_transform = transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])

    train_dataset = datasets.ImageFolder(str(train_dir), transform=train_transform)
    val_dataset = datasets.ImageFolder(str(val_dir), transform=val_transform)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=0)

    return train_loader, val_loader, train_dataset.classes


# ---------------------------------------------------------------------------
# Training helpers
# ---------------------------------------------------------------------------
def train_one_epoch(model, loader, criterion, optimizer, device) -> tuple[float, float]:
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0

    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)
        loss.backward()
        optimizer.step()

        total_loss += loss.item()
        _, predicted = torch.max(outputs, 1)
        correct += (predicted == labels).sum().item()
        total += labels.size(0)

    return total_loss / len(loader), correct / total


def validate(model, loader, criterion, device) -> tuple[float, float]:
    model.eval()
    total_loss = 0.0
    correct = 0
    total = 0

    with torch.no_grad():
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            outputs = model(images)
            loss = criterion(outputs, labels)

            total_loss += loss.item()
            _, predicted = torch.max(outputs, 1)
            correct += (predicted == labels).sum().item()
            total += labels.size(0)

    return total_loss / len(loader), correct / total


# ---------------------------------------------------------------------------
# Optuna objective
# ---------------------------------------------------------------------------
def objective(trial: optuna.Trial, data_path: str, n_epochs: int) -> float:
    """Optuna objective: search PEFT + training hyperparameters."""

    # --- PEFT hyperparameters ---
    lora_r = trial.suggest_categorical("lora_r", [4, 8, 16, 32])
    lora_alpha = trial.suggest_categorical("lora_alpha", [8, 16, 32])
    lora_dropout = trial.suggest_float("lora_dropout", 0.05, 0.2)
    use_dora = trial.suggest_categorical("use_dora", [True, False])

    # --- Training hyperparameters ---
    lr = trial.suggest_float("lr", 1e-4, 1e-2, log=True)
    batch_size = trial.suggest_categorical("batch_size", [16, 32, 64])
    unfreeze_last_n = trial.suggest_int("unfreeze_last_n", 1, 10)

    # Load data
    try:
        train_loader, val_loader, classes = get_dataloaders(data_path, batch_size)
    except Exception as e:
        logger.error("Failed to load data: %s", e)
        return float("inf")

    # Build PEFT model
    from src.ml.models.build_model import build_peft_model

    model = build_peft_model(
        num_classes=len(classes),
        lora_r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        use_dora=use_dora,
        unfreeze_last_n=unfreeze_last_n,
    ).to(DEVICE)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(
        filter(lambda p: p.requires_grad, model.parameters()), lr=lr
    )

    # Train with trial pruning
    best_val_loss = float("inf")
    search_epochs = min(n_epochs, 5)  # Fewer epochs during search

    with mlflow.start_run(nested=True, run_name=f"trial_{trial.number}"):
        mlflow.log_params({
            "lora_r": lora_r,
            "lora_alpha": lora_alpha,
            "lora_dropout": lora_dropout,
            "use_dora": use_dora,
            "lr": lr,
            "batch_size": batch_size,
            "unfreeze_last_n": unfreeze_last_n,
        })

        for epoch in range(search_epochs):
            train_loss, _ = train_one_epoch(model, train_loader, criterion, optimizer, DEVICE)
            val_loss, val_acc = validate(model, val_loader, criterion, DEVICE)

            mlflow.log_metrics({
                "train_loss": train_loss,
                "val_loss": val_loss,
                "val_acc": val_acc,
            }, step=epoch)

            # Report to Optuna for pruning
            trial.report(val_loss, epoch)
            if trial.should_prune():
                raise optuna.TrialPruned()

            best_val_loss = min(best_val_loss, val_loss)

        mlflow.log_metric("best_val_loss", best_val_loss)

    return best_val_loss


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    """Main training: Optuna search → best params → full training → save."""
    config = load_config()
    n_trials = config.get("optuna", {}).get("n_trials", 20)
    n_epochs = config.get("training", {}).get("epochs", 20)

    # Set up MLflow
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("civicpulse-peft-lora")
    logger.info("MLflow URI: %s", MLFLOW_TRACKING_URI)

    # Check data
    if not Path(DATA_PATH).exists():
        logger.error("Data path not found: %s — run: dvc pull -r origin", DATA_PATH)
        sys.exit(1)

    # Run Optuna study (persistent storage)
    storage_url = "sqlite:///optuna.db"
    study = optuna.create_study(
        direction="minimize",
        storage=storage_url,
        study_name="civicpulse-peft",
        load_if_exists=True,
        pruner=optuna.pruners.MedianPruner(),
    )
    logger.info("Starting Optuna study with %d trials", n_trials)
    study.optimize(
        lambda trial: objective(trial, DATA_PATH, n_epochs),
        n_trials=n_trials,
    )

    best_params = study.best_params
    logger.info("Best params: %s", best_params)

    # Train final model with best params
    train_loader, val_loader, classes = get_dataloaders(
        DATA_PATH, best_params.get("batch_size", 32)
    )

    from src.ml.models.build_model import build_peft_model
    from src.ml.training.peft_wrapper import merge_adapter, save_adapter

    model = build_peft_model(
        num_classes=len(classes),
        lora_r=best_params.get("lora_r", 8),
        lora_alpha=best_params.get("lora_alpha", 16),
        lora_dropout=best_params.get("lora_dropout", 0.1),
        use_dora=best_params.get("use_dora", False),
        unfreeze_last_n=best_params.get("unfreeze_last_n", 5),
    ).to(DEVICE)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(
        filter(lambda p: p.requires_grad, model.parameters()),
        lr=best_params.get("lr", 0.001),
    )

    # Final training run in MLflow
    best_val_acc = 0.0
    with mlflow.start_run(run_name="final-peft-model"):
        mlflow.log_params(best_params)
        mlflow.log_param("num_classes", len(classes))
        mlflow.log_param("class_names", str(classes))
        mlflow.log_param("model", "mobilenet_v2_peft")
        mlflow.log_param("peft_method", "dora" if best_params.get("use_dora") else "lora")

        for epoch in range(n_epochs):
            train_loss, train_acc = train_one_epoch(
                model, train_loader, criterion, optimizer, DEVICE
            )
            val_loss, val_acc = validate(model, val_loader, criterion, DEVICE)

            mlflow.log_metrics({
                "train_loss": train_loss,
                "train_acc": train_acc,
                "val_loss": val_loss,
                "val_acc": val_acc,
            }, step=epoch)

            logger.info(
                "Epoch %d/%d: train_loss=%.4f acc=%.4f | val_loss=%.4f acc=%.4f",
                epoch + 1, n_epochs, train_loss, train_acc, val_loss, val_acc,
            )

            if val_acc > best_val_acc:
                best_val_acc = val_acc

        mlflow.log_metric("best_val_acc", best_val_acc)

    # Save adapter weights only (~1-5MB)
    ADAPTER_DIR.mkdir(parents=True, exist_ok=True)
    save_adapter(model, ADAPTER_DIR)

    # Also save merged full model for inference compatibility
    merged = merge_adapter(model)
    model_path = Path("models/model.pth")
    model_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(merged.state_dict(), str(model_path))
    logger.info("Saved merged model to %s (%.2f MB)", model_path, model_path.stat().st_size / 1e6)

    # Export to ONNX for faster CPU inference
    try:
        from src.ml.models.export_onnx import export_to_onnx
        export_to_onnx(num_classes=len(CLASS_NAMES), opset=18)
    except Exception as e:
        logger.warning("ONNX export failed (non-fatal): %s", e)

    # Save metrics
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    metrics = {
        "best_val_acc": best_val_acc,
        "best_params": best_params,
        "peft_method": "dora" if best_params.get("use_dora") else "lora",
    }
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)
    logger.info("Metrics saved to %s", METRICS_PATH)


if __name__ == "__main__":
    main()
