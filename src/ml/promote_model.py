import hydra
from omegaconf import DictConfig
import optuna
import mlflow
import torch
import os
from dotenv import load_dotenv
from ml.training.train import run_training
from common.paths import BEST_MODEL_PATH

load_dotenv()

@hydra.main(config_path="../../configs", config_name="config", version_base=None)
def promote(cfg: DictConfig):
    print("🚀 Starting Model Promotion...")
    
    # 1. Connect to Local Optuna
    storage_url = "sqlite:///optuna.db"
    study_name = cfg.experiment.mlflow.experiment_name
    print(f"📖 Loading Study '{study_name}' from {storage_url}...")
    
    try:
        study = optuna.load_study(study_name=study_name, storage=storage_url)
    except KeyError:
        print(f"❌ Study '{study_name}' not found! Did you run training?")
        return

    # 2. Identify the Winner
    best_trial = study.best_trial
    print(f"🏆 Best Trial Found: Trial {best_trial.number}")
    print(f"   Value (Val Loss): {best_trial.value:.4f}")
    print(f"   Params: {best_trial.params}")

    # 3. Switch MLflow to REMOTE (DagsHub)
    # We temporarily override the config to point to DagsHub
    dagshub_uri = "https://dagshub.com/ram.atchutratna/ai-civic-issue-monitoring.mlflow"
    mlflow.set_tracking_uri(dagshub_uri)
    mlflow.set_experiment(study_name) 
    
    print(f"☁️  Uploading to DagsHub: {dagshub_uri}")

    # 4. Re-Run the Winner (to generate artifacts and upload)
    # We pass the best params back to the trainer
    print("🔄 Re-training/Verifying the winner to generate artifacts...")
    
    # Create a faux trial object or update cfg with best params
    # Updating cfg is safer for reproduction
    cfg.train.learning_rate = best_trial.params['lr']
    # If you had other params, update them here too
    
    # Run WITHOUT 'tune=true' -> runs 'run_training' -> logs to DagsHub
    run_training(cfg, trial=None)

    print("✅ Promotion Complete! Check DagsHub for the 'Production' model.")

if __name__ == "__main__":
    promote()
