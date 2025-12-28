import hydra
from omegaconf import DictConfig
import torch
import torch.nn as nn
import torch.optim as optim
import mlflow
import optuna
from pathlib import Path
from dotenv import load_dotenv
import os

# Load credentials from .env
load_dotenv()

from common.paths import BEST_MODEL_PATH, MODELS_DIR
from ml.data.dataloader import get_dataloaders
from ml.models.model import build_model
from ml.utils.device import get_device
from ml.training.trainer import train_one_epoch, validate_one_epoch


@hydra.main(config_path="../../../configs", config_name="config", version_base=None)
def train(cfg: DictConfig):
    mlflow.set_tracking_uri(cfg.experiment.mlflow.tracking_uri)
    mlflow.set_experiment(cfg.experiment.mlflow.experiment_name)

    if cfg.get("tune", False):
        optimize_hyperparameters(cfg)
    else:
        run_training(cfg)
from ml.evaluation.evaluator import evaluate_model

def run_training(cfg: DictConfig, trial=None):
    device = get_device()
    train_loader, val_loader, test_loader, classes = get_dataloaders(cfg.data.data_dir, cfg.train.batch_size)

    # If tuning, use trial suggested values
    lr = cfg.train.learning_rate if trial is None else trial.suggest_float("lr", 1e-4, 1e-2, log=True)
    
    unfreeze_last_n = cfg.model.get("unfreeze_last_n", 0)
    
    model = build_model(
        len(classes), 
        unfreeze_last_n=unfreeze_last_n
    ).to(device)

    # 📥 LOAD CHECKPOINT (For Fine-Tuning Phase 1 weights)
    checkpoint_path = cfg.model.get("checkpoint_path", None)
    if checkpoint_path:
        checkpoint_path = Path(checkpoint_path)
        if checkpoint_path.exists():
            print(f"📂 Loading checkpoint from {checkpoint_path}...")
            state_dict = torch.load(checkpoint_path, map_location=device)
            # Use our robust loader (handles classifier shape if needed)
            from ml.models.model import robust_load_state_dict
            robust_load_state_dict(model, state_dict)
        else:
            print(f"⚠️ Warning: Checkpoint {checkpoint_path} not found. Starting from scratch.")
    
    # Calculate class weights for imbalanced dataset
    # Get class distribution from training data
    from collections import Counter
    train_dataset = train_loader.dataset
    
    # Handle Subset wrapper (used in dataloader splits)
    if hasattr(train_dataset, 'dataset'):
        actual_dataset = train_dataset.dataset
        indices = train_dataset.indices
        class_counts = Counter([actual_dataset.targets[i] for i in indices])
    else:
        class_counts = Counter(train_dataset.targets)
    
    # Calculate weights: weight_i = total_samples / (num_classes * count_i)
    total_samples = sum(class_counts.values())
    num_classes = len(classes)
    
    class_weights = torch.tensor([
        total_samples / (num_classes * class_counts[i]) 
        for i in range(num_classes)
    ], dtype=torch.float32).to(device)
    
    criterion = nn.CrossEntropyLoss(weight=class_weights)
    
    print(f"\n📊 Class Distribution:")
    for i, cls in enumerate(classes):
        print(f"  {cls:12}: {class_counts[i]:4} samples (weight: {class_weights[i]:.2f})")
    print()
    
    # 🧠 SMART OPTIMIZER:
    # Dynamically pick ONLY the parameters that are unfrozen (requires_grad=True)
    params_to_update = [p for p in model.parameters() if p.requires_grad]
    optimizer = optim.Adam(params_to_update, lr=lr)

    with mlflow.start_run(nested=(trial is not None)):
        mlflow.log_params({
            "epochs": cfg.train.epochs,
            "batch_size": cfg.train.batch_size,
            "learning_rate": lr,
            "is_tuning": trial is not None
        })

        best_loss = float("inf")
        for epoch in range(cfg.train.epochs):
            # 1. Train
            train_loss = train_one_epoch(model, train_loader, optimizer, criterion, device)
            
            # 2. Validate (The Missing Piece!)
            val_loss = validate_one_epoch(model, val_loader, criterion, device)
            
            # Log both
            mlflow.log_metrics({
                "train_loss": train_loss,
                "val_loss": val_loss
            }, step=epoch)
            
            print(f"📊 Epoch {epoch} Summary: Train Loss: {train_loss:.4f} | Val Loss: {val_loss:.4f}")
            
            # Optuna should minimize VAL loss, not TRAIN loss
            if val_loss < best_loss:
                best_loss = val_loss
                if trial is None:
                    BEST_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
                    torch.save(model.state_dict(), BEST_MODEL_PATH)

            # Report intermediate objective value to Optuna for pruning
            if trial is not None:
                trial.report(val_loss, epoch)
                if trial.should_prune():
                    raise optuna.exceptions.TrialPruned()

        if trial is None:
            # Phase 4: Final Evaluation on Test Set (The True Benchmark)
            print("🚀 Running Final Evaluation on Blind Test Set...")
            evaluate_model(model, test_loader, classes)
            mlflow.log_artifact(str(BEST_MODEL_PATH))

    return best_loss

def optimize_hyperparameters(cfg: DictConfig):
    def objective(trial):
        return run_training(cfg, trial=trial)

    # Use persistent storage so we can resume if interrupted
    storage_url = "sqlite:///optuna.db"
    study = optuna.create_study(
        direction="minimize",
        storage=storage_url,
        study_name=cfg.experiment.mlflow.experiment_name,
        load_if_exists=True
    )
    
    print(f"💾 Optuna Study '{cfg.experiment.mlflow.experiment_name}' stored in {storage_url}")
    study.optimize(objective, n_trials=cfg.train.n_trials)

    print(f"Best value: {study.best_value} (params: {study.best_params})")
    mlflow.log_params(study.best_params)


if __name__ == "__main__":
    train()
