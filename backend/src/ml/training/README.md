# Training Environment Setup

Training requires mlflow which conflicts with the main pixi environment.
Use a separate Python venv for training:

## Setup
```bash
cd backend
python -m venv .venv-train
.venv-train\Scripts\activate  # Windows
pip install torch torchvision mlflow optuna peft scikit-learn pandas pillow pyyaml
```

## Pull Training Data (5GB)
```bash
cd ..
dvc pull -r origin --jobs 4
```

## Configure DagsHub MLflow
Set environment variables before training:
```bash
set MLFLOW_TRACKING_URI=<your-dagshub-mlflow-uri>
set MLFLOW_TRACKING_USERNAME=<your-username>
set MLFLOW_TRACKING_PASSWORD=<your-password>
set DATA_PATH=data/raw
```

## Run Training
```bash
cd backend
python -m src.ml.training.train
```

## What happens:
1. Optuna searches PEFT hyperparameters (lora_r, lora_alpha, use_dora, lora_dropout, lr, batch_size)
2. Each trial trains MobileNetV2 + LoRA/DoRA adapter (5 epochs during search)
3. Best params found → final training for 20 epochs
4. All metrics logged to DagsHub MLflow
5. Saves adapter weights to `models/adapter/` (~1-5MB)
6. Saves merged model to `models/model.pth` (~9MB)
7. Backend automatically loads adapter on restart

## PEFT Methods
- **LoRA**: Low-Rank Adaptation — adds small trainable matrices to existing layers
- **DoRA**: Weight-Decomposed Low-Rank Adaptation — slightly better accuracy, ~2x slower

## Classes (alphabetical, matching ImageFolder):
- debris
- garbage  
- non_civic
- pothole
