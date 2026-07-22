# Training Environment Setup

Training requires mlflow and optuna which conflict with the main pixi environment.
Use a separate Python venv for training:

## Setup
```bash
cd backend
python -m venv .venv-train
.venv-train\Scripts\activate  # Windows
pip install torch torchvision mlflow optuna scikit-learn pandas pillow
```

## Pull Training Data (5GB)
```bash
cd ..
dvc pull -r origin --jobs 4
```

## Configure DagsHub MLflow
Set environment variables before training:
```bash
set MLFLOW_TRACKING_URI=https://dagshub.com/ram.atchutratna/ai-civic-issue-monitoring.mlflow
set MLFLOW_TRACKING_USERNAME=ram.atchutratna@gmail.com
set MLFLOW_TRACKING_PASSWORD=Ram@1126
set DATA_PATH=data/balanced_gold
```

## Run Training
```bash
cd backend
python -m src.ml.training.train
```

## What happens:
1. Optuna tunes hyperparameters (lr, batch_size, unfreeze_last_n)
2. Trains MobileNetV2 with transfer learning (20 epochs)
3. Logs metrics to DagsHub MLflow
4. Saves best model to `models/model.pth`
5. Backend automatically picks up the new model on restart

## Classes (alphabetical, matching ImageFolder):
- debris
- garbage  
- non_civic
- pothole
