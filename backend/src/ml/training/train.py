"""Training pipeline for CivicPulse issue classifier.

Uses MobileNetV2 with PEFT adapters (LoRA/DoRA family + alternatives).
Hyperparameter search via Optuna with persistent storage; the objective is
val macro-F1 (not raw accuracy, which is misleading under class imbalance).
The winning config is retrained on train+val combined and evaluated exactly
once on a content-deduplicated held-out test split. All runs are tracked on
DagsHub MLflow.
"""

from __future__ import annotations

import json
import logging
import os
import random
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import mlflow
import mlflow.pytorch
import numpy as np
import optuna
import torch
import torch.nn as nn
import torch.optim as optim
import yaml
from mlflow.models.signature import ModelSignature
from mlflow.types.schema import Schema, TensorSpec
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from torch.utils.data import ConcatDataset, DataLoader
from torchvision import datasets, transforms
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    force=True,  # some imported libs add a NullHandler to root; force ensures INFO is visible
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
NUM_CLASSES = 4
CLASS_NAMES = ["debris", "garbage", "non_civic", "pothole"]
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
SEED = int(os.getenv("TRAIN_SEED", "42"))

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "")
MLFLOW_EXPERIMENT = os.getenv("TRAIN_EXPERIMENT", "civicpulse-peft-v3")
DATA_PATH = os.getenv("DATA_PATH", "data/raw")
CONFIG_PATH = Path(__file__).resolve().parent.parent.parent.parent / "configs" / "training.yaml"
ADAPTER_DIR = Path("models/adapter")
METRICS_PATH = Path("metrics/train.json")

TARGET_MODULES_STR = "features.14.conv.2,features.15.conv.2,features.16.conv.2"


def load_config() -> dict:
    """Load training config (search space + run settings) from YAML."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f)
    return {}


# --- Search space ("grocery list") from configs/training.yaml ---
# Fallback defaults keep the script runnable even if the YAML is missing.
_CONFIG = load_config()
_SEARCH = _CONFIG.get("search", {})
PEFT_METHODS = _SEARCH.get(
    "peft_methods",
    [
        "dora",
        "dora",
        "dora",
        "dora_plus",
        "dora_plus",
        "dora_plus",
        "lora",
        "lora",
        "lora_plus",
        "lora_plus",
        "rslora",
        "rslora",
        "lora_fa",
        "adalora",
        "oft",
        "boft",
        "loha",
        "lokr",
        "ia3",
    ],
)
LORA_R_OPTIONS = _SEARCH.get("lora_r", [8, 16])
LORA_DROPOUT_OPTIONS = _SEARCH.get("lora_dropout", [0.0, 0.05])
_LR = _SEARCH.get("lr", {})
LR_MIN = _LR.get("min", 5e-4)
LR_MAX = _LR.get("max", 1e-2)
LR_LOG = _LR.get("log", True)
BATCH_SIZE_OPTIONS = _SEARCH.get("batch_size", [32, 64])
UNFREEZE_OPTIONS = _SEARCH.get("unfreeze_last_n", [0, 3])
LORAPLUS_RATIO = _CONFIG.get("loraplus_ratio", 16.0)
CLASS_BALANCE_BETA = _CONFIG.get("class_balance_beta", 0.999)


def seed_everything(seed: int) -> None:
    """Seed all RNGs for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def make_train_transform() -> transforms.Compose:
    return transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.RandomHorizontalFlip(),
            transforms.RandomRotation(15),
            transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )


def make_val_transform() -> transforms.Compose:
    return transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )


def get_dataloaders(data_path: str, batch_size: int) -> tuple[DataLoader, DataLoader, DataLoader | None, list[str]]:
    """Load train/val/test data from data/raw directory.

    Returns (train_loader, val_loader, test_loader, classes). test_loader is
    None when no test split exists.
    """
    train_dir = Path(data_path) / "train"
    val_dir = Path(data_path) / "val"
    test_dir = Path(data_path) / "test"

    train_transform = make_train_transform()
    val_transform = make_val_transform()

    train_dataset = datasets.ImageFolder(str(train_dir), transform=train_transform)
    val_dataset = datasets.ImageFolder(str(val_dir), transform=val_transform)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=0)

    test_loader = None
    if test_dir.exists():
        test_dataset = datasets.ImageFolder(str(test_dir), transform=val_transform)
        test_loader = DataLoader(test_dataset, batch_size=batch_size, shuffle=False, num_workers=0)

    return train_loader, val_loader, test_loader, train_dataset.classes


def get_combined_dataloaders(data_path: str, batch_size: int) -> tuple[DataLoader, DataLoader | None, list[str]]:
    """train+val combined (for final training); test kept for final eval."""
    train_loader, val_loader, test_loader, classes = get_dataloaders(data_path, batch_size)

    combined = ConcatDataset(
        [
            datasets.ImageFolder(str(Path(data_path) / "train"), transform=make_train_transform()),
            datasets.ImageFolder(str(Path(data_path) / "val"), transform=make_train_transform()),
        ]
    )
    combined_loader = DataLoader(combined, batch_size=batch_size, shuffle=True, num_workers=0)

    return combined_loader, test_loader, classes


def count_class_images(data_path: str, split: str) -> list[int]:
    """Per-class image counts for a split, in ImageFolder class order."""
    d = Path(data_path) / split
    if not d.exists():
        return [0] * NUM_CLASSES
    ds = datasets.ImageFolder(str(d))
    return [sum(1 for t in ds.targets if t == i) for i in range(len(ds.classes))]


def class_balanced_weights(counts: list[int], beta: float = CLASS_BALANCE_BETA) -> list[float]:
    """Cui et al. class-balanced inverse-frequency weights, normalized to mean 1."""
    weights = []
    for c in counts:
        effective_num = 1.0 - beta ** max(c, 1)
        weights.append((1.0 - beta) / effective_num)
    mean = sum(weights) / len(weights)
    return [w / mean for w in weights]


# ---------------------------------------------------------------------------
# PEFT method search space is defined in configs/training.yaml (search section),
# loaded above into PEFT_METHODS / LORA_R_OPTIONS / LORA_DROPOUT_OPTIONS /
# LR_MIN / LR_MAX / LR_LOG / BATCH_SIZE_OPTIONS / UNFREEZE_OPTIONS.
# ---------------------------------------------------------------------------


def build_optimizer(model, lr: float, peft_method: str):
    """Build Adam. LoRA+/DoRA+ train lora_B at lr*ratio and lora_A at lr."""
    if peft_method in ("lora_plus", "dora_plus"):
        a_params = [p for n, p in model.named_parameters() if p.requires_grad and "lora_A" in n]
        b_params = [p for n, p in model.named_parameters() if p.requires_grad and "lora_A" not in n]
        return optim.Adam(
            [
                {"params": a_params, "lr": lr},
                {"params": b_params, "lr": lr * LORAPLUS_RATIO},
            ]
        )
    return optim.Adam(filter(lambda p: p.requires_grad, model.parameters()), lr=lr)


def count_trainable(model) -> tuple[int, int, float]:
    """(trainable, total, trainable_pct) parameter counts."""
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    pct = (100.0 * trainable / total) if total else 0.0
    return trainable, total, pct


def git_commit() -> str:
    """Current HEAD hash for reproducibility."""
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"


def safe_log_params(params: dict) -> None:
    """Log params to MLflow without crashing training if tracking is offline."""
    try:
        mlflow.log_params(params)
    except Exception as e:
        logger.warning("MLflow log_params failed (offline?): %s", e)


def safe_log_metrics(metrics: dict, step: int | None = None) -> None:
    """Log metrics to MLflow without crashing training if tracking is offline."""
    try:
        if step is None:
            mlflow.log_metrics(metrics)
        else:
            mlflow.log_metrics(metrics, step=step)
    except Exception as e:
        logger.warning("MLflow log_metrics failed (offline?): %s", e)


# ---------------------------------------------------------------------------
# Training helpers
# ---------------------------------------------------------------------------
def train_one_epoch(
    model, loader, criterion, optimizer, device, epoch: int = 0, n_epochs: int = 0
) -> tuple[float, float]:
    model.train()
    total_loss = 0.0
    correct = 0
    total = 0
    desc = f"Train epoch {epoch}/{n_epochs}" if n_epochs else "Train"

    pbar = tqdm(loader, desc=desc, leave=False)
    for images, labels in pbar:
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
        pbar.set_postfix(loss=f"{total_loss / (pbar.n + 1):.4f}", acc=f"{correct / total:.4f}")

    return total_loss / len(loader), correct / total


def evaluate_metrics(model, loader, criterion, device, num_classes: int) -> dict:
    """Full metrics (loss, acc, macro-F1, per-class P/R/F1, confusion matrix)."""
    model.eval()
    total_loss = 0.0
    all_true: list[np.ndarray] = []
    all_pred: list[np.ndarray] = []

    with torch.no_grad():
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            outputs = model(images)
            total_loss += criterion(outputs, labels).item() * labels.size(0)
            _, pred = torch.max(outputs, 1)
            all_true.append(labels.cpu().numpy())
            all_pred.append(pred.cpu().numpy())

    if not all_true:
        return {"loss": float("inf"), "acc": 0.0, "macro_f1": 0.0}

    y_true = np.concatenate(all_true)
    y_pred = np.concatenate(all_pred)
    n = len(y_true)
    labels = list(range(num_classes))

    return {
        "loss": total_loss / n,
        "acc": accuracy_score(y_true, y_pred),
        "macro_f1": f1_score(y_true, y_pred, average="macro", zero_division=0),
        "per_class_precision": precision_score(y_true, y_pred, average=None, labels=labels, zero_division=0),
        "per_class_recall": recall_score(y_true, y_pred, average=None, labels=labels, zero_division=0),
        "per_class_f1": f1_score(y_true, y_pred, average=None, labels=labels, zero_division=0),
        "confusion": confusion_matrix(y_true, y_pred, labels=labels),
    }


# ---------------------------------------------------------------------------
# Optuna objective
# ---------------------------------------------------------------------------
def objective(trial: optuna.Trial, data_path: str, n_epochs: int) -> float:
    """Optuna objective: maximize val macro-F1."""
    seed_everything(SEED + trial.number)

    # --- PEFT method ---
    peft_method = trial.suggest_categorical("peft_method", PEFT_METHODS)

    # --- PEFT hyperparameters (research-informed priors) ---
    from src.ml.training.peft_wrapper import RANK_METHODS

    if peft_method in RANK_METHODS:
        lora_r = trial.suggest_categorical("lora_r", LORA_R_OPTIONS)
        lora_alpha = 2 * lora_r  # standard alpha=2r recipe, not searched
    else:
        lora_r, lora_alpha = 8, 16

    if peft_method in ("lora", "dora", "rslora", "lora_fa", "lora_plus", "dora_plus", "adalora"):
        lora_dropout = trial.suggest_categorical("lora_dropout", LORA_DROPOUT_OPTIONS)
    else:
        lora_dropout = 0.0

    # --- Training hyperparameters ---
    lr = trial.suggest_float("lr", LR_MIN, LR_MAX, log=LR_LOG)
    batch_size = trial.suggest_categorical("batch_size", BATCH_SIZE_OPTIONS)
    unfreeze_last_n = trial.suggest_categorical("unfreeze_last_n", UNFREEZE_OPTIONS)

    # Load data
    try:
        train_loader, val_loader, _, classes = get_dataloaders(data_path, batch_size)
    except Exception as e:
        logger.error("Failed to load data: %s", e)
        return float("-inf")

    search_epochs = min(n_epochs, 5)  # Fewer epochs during search
    total_step = search_epochs * len(train_loader)  # AdaLoRA rank scheduler

    # Build PEFT model
    from src.ml.models.build_model import build_peft_model

    model = build_peft_model(
        num_classes=len(classes),
        method=peft_method,
        lora_r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        unfreeze_last_n=unfreeze_last_n,
        total_step=total_step,
    ).to(DEVICE)

    # Class-balanced loss from the training split
    train_counts = count_class_images(data_path, "train")
    weights = class_balanced_weights(train_counts)
    criterion = nn.CrossEntropyLoss(weight=torch.tensor(weights, dtype=torch.float32).to(DEVICE))
    optimizer = build_optimizer(model, lr, peft_method)

    trainable, total_params, trainable_pct = count_trainable(model)

    best_val_loss = float("inf")
    best_val_acc = 0.0
    best_val_f1 = 0.0

    run = None
    try:
        run = mlflow.start_run(nested=True, run_name=f"trial_{trial.number}")
    except Exception as e:
        logger.warning("MLflow start_run failed (offline?); trial continues unlogged: %s", e)

    if run is not None:
        safe_log_params(
            {
                "peft_method": peft_method,
                "lora_r": lora_r,
                "lora_alpha": lora_alpha,
                "lora_dropout": lora_dropout,
                "loraplus_ratio": LORAPLUS_RATIO,
                "lr": lr,
                "batch_size": batch_size,
                "unfreeze_last_n": unfreeze_last_n,
                "optimizer": "Adam",
                "target_modules": TARGET_MODULES_STR,
                "trainable_params": trainable,
                "total_params": total_params,
                "trainable_pct": round(trainable_pct, 4),
                "seed": SEED + trial.number,
                "class_balance_beta": CLASS_BALANCE_BETA,
            }
        )

    for epoch in range(search_epochs):
        train_loss, _ = train_one_epoch(model, train_loader, criterion, optimizer, DEVICE, epoch + 1, search_epochs)
        val = evaluate_metrics(model, val_loader, criterion, DEVICE, len(classes))
        val_loss, val_acc, val_f1 = val["loss"], val["acc"], val["macro_f1"]

        if run is not None:
            safe_log_metrics(
                {
                    "train_loss": train_loss,
                    "val_loss": val_loss,
                    "val_acc": val_acc,
                    "val_macro_f1": val_f1,
                },
                step=epoch,
            )

        # Report to Optuna (NopPruner means this never prunes; keeps the
        # comparison fair across slow/fast-converging methods).
        trial.report(val_f1, epoch)
        if trial.should_prune():
            raise optuna.TrialPruned()

        best_val_loss = min(best_val_loss, val_loss)
        best_val_acc = max(best_val_acc, val_acc)
        best_val_f1 = max(best_val_f1, val_f1)

    if run is not None:
        safe_log_metrics(
            {
                "best_val_loss": best_val_loss,
                "best_val_acc": best_val_acc,
                "best_val_macro_f1": best_val_f1,
            }
        )
        try:
            mlflow.end_run()
        except Exception:
            pass

    logger.info(
        "Trial %d (%s r=%s lr=%.5f bs=%s): best_val_f1=%.4f acc=%.4f",
        trial.number,
        peft_method,
        lora_r,
        lr,
        batch_size,
        best_val_f1,
        best_val_acc,
    )
    return best_val_f1


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    """Main training: Optuna search → best params → full training → test eval."""
    t0 = time.time()
    seed_everything(SEED)

    config = load_config()
    # Env-var overrides allow right-sizing CPU/GPU runs without editing config.
    n_trials = int(os.getenv("TRAIN_N_TRIALS", config.get("optuna", {}).get("n_trials", 20)))
    n_epochs = int(os.getenv("TRAIN_EPOCHS", config.get("training", {}).get("epochs", 20)))
    final_epochs = int(os.getenv("TRAIN_FINAL_EPOCHS", str(n_epochs)))

    # Set up MLflow
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT)
    logger.info("MLflow URI: %s | experiment: %s", MLFLOW_TRACKING_URI, MLFLOW_EXPERIMENT)

    # Check data
    if not Path(DATA_PATH).exists():
        logger.error("Data path not found: %s — run: dvc pull -r origin", DATA_PATH)
        sys.exit(1)

    # Run Optuna study (persistent storage). A fresh study/storage per search
    # design keeps old trials (with a different search space) from contaminating
    # TPE. NopPruner keeps the method comparison fair.
    storage_url = os.getenv("TRAIN_STUDY_STORAGE", config.get("optuna", {}).get("storage", "sqlite:///optuna_v3.db"))
    study_name = os.getenv("TRAIN_STUDY_NAME", config.get("optuna", {}).get("study_name", "civicpulse-peft-v3"))
    study = optuna.create_study(
        direction=config.get("optuna", {}).get("direction", "maximize"),
        storage=storage_url,
        study_name=study_name,
        load_if_exists=True,
        pruner=optuna.pruners.NopPruner(),
    )
    logger.info("Starting Optuna study %s with %d trials (%d epochs each)", study_name, n_trials, n_epochs)
    study.optimize(
        lambda trial: objective(trial, DATA_PATH, n_epochs),
        n_trials=n_trials,
        # A failed trial (e.g. MLflow offline, transient error) is recorded as
        # FAILED and the study continues instead of aborting the whole run.
        catch=(Exception,),
    )

    best_params = study.best_params
    logger.info("Best params: %s (best val macro-F1: %.4f)", best_params, study.best_value)

    if final_epochs <= 0:
        # Search-only mode: stop after the trials, do NOT retrain on train+val.
        logger.info("TRAIN_FINAL_EPOCHS=%d: final retraining skipped (search only)", final_epochs)
        METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        metrics = {
            "best_val_macro_f1": study.best_value,
            "best_params": best_params,
            "peft_method": best_params.get("peft_method", "lora"),
            "git_commit": git_commit(),
            "final_retraining": "skipped",
            "duration_minutes": round((time.time() - t0) / 60.0, 2),
        }
        with open(METRICS_PATH, "w") as f:
            json.dump(metrics, f, indent=2)
        logger.info("Search complete. Metrics saved to %s", METRICS_PATH)
        return

    # Train final model with best params on train+val combined.
    combined_loader, test_loader, classes = get_combined_dataloaders(DATA_PATH, best_params.get("batch_size", 32))

    from src.ml.models.build_model import build_peft_model
    from src.ml.training.peft_wrapper import merge_adapter, save_adapter

    peft_method = best_params.get("peft_method", "lora")

    model = build_peft_model(
        num_classes=len(classes),
        method=peft_method,
        lora_r=best_params.get("lora_r", 8),
        lora_alpha=best_params.get("lora_alpha", 16),
        lora_dropout=best_params.get("lora_dropout", 0.0),
        unfreeze_last_n=best_params.get("unfreeze_last_n", 5),
        total_step=final_epochs * len(combined_loader),
    ).to(DEVICE)

    trainable, total_params, trainable_pct = count_trainable(model)

    # Class-balanced weights from the final training pool (train+val).
    final_counts = [
        a + b
        for a, b in zip(
            count_class_images(DATA_PATH, "train"),
            count_class_images(DATA_PATH, "val"),
        )
    ]
    weights = class_balanced_weights(final_counts)
    criterion = nn.CrossEntropyLoss(weight=torch.tensor(weights, dtype=torch.float32).to(DEVICE))
    optimizer = build_optimizer(model, best_params.get("lr", 0.001), peft_method)

    train_counts = count_class_images(DATA_PATH, "train")
    val_counts = count_class_images(DATA_PATH, "val")
    test_counts = count_class_images(DATA_PATH, "test")

    # Final training run in MLflow
    run_id = None
    active_run = None
    try:
        active_run = mlflow.start_run(run_name="final-peft-model")
        run_id = active_run.info.run_id
    except Exception as e:
        logger.warning("MLflow start_run failed (offline?); final training continues unlogged: %s", e)

    if active_run is not None:
        safe_log_params(best_params)
        safe_log_params(
            {
                "loraplus_ratio": LORAPLUS_RATIO,
                "optimizer": "Adam",
                "target_modules": TARGET_MODULES_STR,
                "model": "mobilenet_v2_peft",
                "num_classes": len(classes),
                "class_names": str(classes),
                "git_commit": git_commit(),
                "device": str(DEVICE),
                "seed": SEED,
                "objective": "val_macro_f1",
                "total_trials": n_trials,
                "final_epochs": final_epochs,
                "trainable_params": trainable,
                "total_params": total_params,
                "trainable_pct": round(trainable_pct, 4),
                "class_balance_beta": CLASS_BALANCE_BETA,
                "class_weights": json.dumps({c: round(w, 4) for c, w in zip(classes, weights)}),
                "dataset_train": sum(train_counts),
                "dataset_val": sum(val_counts),
                "dataset_test": sum(test_counts),
            }
        )

    for epoch in range(final_epochs):
        train_loss, train_acc = train_one_epoch(
            model, combined_loader, criterion, optimizer, DEVICE, epoch + 1, final_epochs
        )
        if active_run is not None:
            safe_log_metrics(
                {
                    "train_loss": train_loss,
                    "train_acc": train_acc,
                },
                step=epoch,
            )
        logger.info(
            "Final epoch %d/%d: train_loss=%.4f acc=%.4f",
            epoch + 1,
            final_epochs,
            train_loss,
            train_acc,
        )

    # One final reference pass on val (val is now in-training; reported for
    # comparison with the search, not as the headline number).
    val_loader = get_dataloaders(DATA_PATH, best_params.get("batch_size", 32))[1]
    val = evaluate_metrics(model, val_loader, criterion, DEVICE, len(classes))
    if active_run is not None:
        safe_log_metrics(
            {
                "val_loss": val["loss"],
                "val_acc": val["acc"],
                "val_macro_f1": val["macro_f1"],
            }
        )

    # THE single test evaluation — the honest generalization score.
    test_result = None
    if test_loader is not None:
        tm = evaluate_metrics(model, test_loader, criterion, DEVICE, len(classes))
        test_result = tm
        if active_run is not None:
            metrics_to_log = {
                "test_loss": tm["loss"],
                "test_acc": tm["acc"],
                "test_macro_f1": tm["macro_f1"],
            }
            for i, cls in enumerate(classes):
                metrics_to_log[f"test_{cls}_precision"] = float(tm["per_class_precision"][i])
                metrics_to_log[f"test_{cls}_recall"] = float(tm["per_class_recall"][i])
                metrics_to_log[f"test_{cls}_f1"] = float(tm["per_class_f1"][i])
            safe_log_metrics(metrics_to_log)

            cm_path = Path("metrics/test_confusion_matrix.json")
            cm_path.parent.mkdir(parents=True, exist_ok=True)
            cm_path.write_text(
                json.dumps(
                    {"confusion_matrix": tm["confusion"].tolist(), "labels": classes},
                    indent=2,
                ),
                encoding="utf-8",
            )
            try:
                mlflow.log_artifact(str(cm_path), artifact_path="metrics")
            except Exception as e:
                logger.warning("MLflow log_artifact failed (offline?): %s", e)
            logger.info(
                "TEST eval: loss=%.4f acc=%.4f macro_f1=%.4f",
                tm["loss"],
                tm["acc"],
                tm["macro_f1"],
            )

    if active_run is not None:
        try:
            mlflow.end_run()
        except Exception:
            pass

    # Save adapter weights BEFORE any merge: merge_and_unload() removes the
    # adapter from the PeftModel, so saving after merging yields an empty file.
    ADAPTER_DIR.mkdir(parents=True, exist_ok=True)
    save_adapter(model, ADAPTER_DIR)

    # Log merged model artifact into the same final run (registry ready).
    try:
        merged_log = merge_adapter(model)
        mlflow.start_run(run_id=run_id)
        model_signature = ModelSignature(
            inputs=Schema([TensorSpec(np.dtype("float32"), (-1, 3, 224, 224), "input")]),
            outputs=Schema([TensorSpec(np.dtype("float32"), (-1, len(CLASS_NAMES)), "output")]),
        )
        # DagsHub's MLflow server does not support the 3.x "logged model" store, so
        # mlflow.pytorch.log_model uploads nothing there. Use the classic
        # save_model + log_artifacts path so the model artifact is downloadable.
        with tempfile.TemporaryDirectory(prefix="mlflow_model_") as model_dir:
            mlflow.pytorch.save_model(
                merged_log,
                path=model_dir,
                input_example=torch.randn(1, 3, 224, 224),
                signature=model_signature,
                serialization_format=mlflow.pytorch.SERIALIZATION_FORMAT_PT2,
            )
            mlflow.log_artifacts(model_dir, artifact_path="model")
        mlflow.end_run()
    except Exception as e:
        logger.warning("MLflow model artifact logging failed (non-fatal): %s", e)

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
    duration_minutes = (time.time() - t0) / 60.0
    metrics = {
        "best_val_macro_f1": study.best_value,
        "best_params": best_params,
        "peft_method": peft_method,
        "git_commit": git_commit(),
        "duration_minutes": round(duration_minutes, 2),
    }
    if test_result is not None:
        metrics["test_acc"] = test_result["acc"]
        metrics["test_macro_f1"] = test_result["macro_f1"]
        metrics["test_per_class_f1"] = {cls: float(test_result["per_class_f1"][i]) for i, cls in enumerate(classes)}
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)
    logger.info("Metrics saved to %s", METRICS_PATH)


if __name__ == "__main__":
    main()
