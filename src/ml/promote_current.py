import hydra
from omegaconf import DictConfig
import mlflow
import torch
from dotenv import load_dotenv

from common.paths import BEST_MODEL_PATH
from ml.data.dataloader import get_dataloaders
from ml.models.model import build_model, robust_load_state_dict
from ml.utils.device import get_device
from ml.evaluation.evaluator import evaluate_model

load_dotenv()

@hydra.main(config_path="../../configs", config_name="config", version_base=None)
def promote_current(cfg: DictConfig):
    print("🚀 Promoting CURRENT Local Model to DagsHub...")
    
    if not BEST_MODEL_PATH.exists():
        print(f"❌ Error: {BEST_MODEL_PATH} not found. Train a model first!")
        return

    device = get_device()
    train_loader, val_loader, test_loader, classes = get_dataloaders(cfg.data.data_dir, cfg.train.batch_size)
    
    # 1. Load the model
    model = build_model(len(classes)).to(device)
    print(f"📂 Loading weights from {BEST_MODEL_PATH}")
    state_dict = torch.load(BEST_MODEL_PATH, map_location=device)
    robust_load_state_dict(model, state_dict)
    model.eval()

    # 2. Switch to DagsHub
    dagshub_uri = "https://dagshub.com/ram.atchutratna/ai-civic-issue-monitoring.mlflow"
    mlflow.set_tracking_uri(dagshub_uri)
    mlflow.set_experiment(cfg.experiment.mlflow.experiment_name)
    
    print("☁️  Uploading to DagsHub as a new run...")
    
    with mlflow.start_run(run_name="manual-promotion"):
        # Log what we know
        mlflow.log_param("promotion_type", "manual_current")
        mlflow.log_param("classes", classes)
        
        # 3. Evaluate on test set to get metrics on DagsHub
        print("📊 Measuring performance for DagsHub metrics...")
        evaluate_model(model, test_loader, classes)
        
        # 4. Upload the artifact
        mlflow.log_artifact(str(BEST_MODEL_PATH))
        print("✅ Promotion Complete! Metrics and model are now on DagsHub.")

if __name__ == "__main__":
    promote_current()
