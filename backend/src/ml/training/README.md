# Training Environment Setup

## Recommended: the pixi `ml` environment

The `ml` feature already carries `torch`, `torchvision`, `mlflow`, `optuna`,
`peft`, `scikit-learn` and the rest of the training stack, so no separate venv
is needed:

```bash
pixi install -e ml
```

<details>
<summary>Alternative: a standalone venv</summary>

```bash
python -m venv .venv-train
.venv-train\Scripts\activate  # Windows
. .venv-train/bin/activate    # POSIX
pip install torch torchvision mlflow optuna peft scikit-learn pandas pillow pyyaml
```

</details>

## Pull Training Data (5GB)

```bash
# from the repository root
dvc pull -r origin --jobs 4
```

`dvc pull` writes `data/raw`, `models/` and `metrics/` at the **repository
root**.

## Configure DagsHub MLflow

Set environment variables before training:

```bash
set MLFLOW_TRACKING_URI=<your-dagshub-mlflow-uri>
set MLFLOW_TRACKING_USERNAME=<your-username>
set MLFLOW_TRACKING_PASSWORD=<your-password>
set DATA_PATH=data/raw
```

## Run Training

Training must be started from the **repository root**, not from `backend/`.
`train.py` resolves `DATA_PATH`, `models/adapter` and `metrics/train.json`
relative to the current working directory, and `dvc pull` lays all three down
at the root — running from `backend/` makes `Path("data/raw")` resolve to a
directory that does not exist and exits at the data check.

```bash
# from the repository root
pixi run train
# equivalent:
PYTHONPATH=backend python -m src.ml.training.train
```

## What happens

1. Optuna searches the PEFT hyperparameters declared in
   `configs/training.yaml` — `peft_methods`, `lora_r`, `lora_dropout`, `lr`,
   `batch_size`, `unfreeze_last_n`. (`lora_alpha` is *not* searched: the
   `alpha = 2 * r` recipe fixes it from `lora_r`.)
2. Each trial trains MobileNetV2 + the chosen adapter for
   `training.epochs` (4) epochs, scoring val macro-F1.
3. Best params found → final training, then exactly one evaluation on a
   content-deduplicated held-out test split. `TRAIN_FINAL_EPOCHS` overrides
   the epoch count (`0` skips the final pass).
4. All metrics logged to DagsHub MLflow.
5. Saves adapter weights to `models/adapter/` (~1-5MB).
6. Saves the merged model to `models/model.pth` (~9MB).
7. The backend reloads the adapter on restart — see `_get_torch_model()` in
   `src/ml/inference/predict.py`, which prefers `models/adapter/` over
   `models/model.pth` and falls back to the ONNX export when neither exists.

## Env overrides

| Variable | Falls back to | Meaning |
| --- | --- | --- |
| `TRAIN_N_TRIALS` | `optuna.n_trials` (15) | Optuna trials; `0` = reuse an existing study |
| `TRAIN_EPOCHS` | `training.epochs` (4) | Epochs per trial during the search |
| `TRAIN_FINAL_EPOCHS` | `TRAIN_EPOCHS` | Epochs for the final fit; `0` = search only |
| `TRAIN_STUDY_STORAGE` | `optuna.storage` | Optuna storage URL |
| `TRAIN_STUDY_NAME` | `optuna.study_name` | Optuna study name |
| `DATA_PATH` | `data/raw` | Dataset root (train/val/test) |

An empty or unset variable falls back to the config value, which is why one
workflow file can drive both `workflow_dispatch` and Prefect-triggered pushes.

## PEFT Methods

- **LoRA**: Low-Rank Adaptation — adds small trainable matrices to existing layers
- **DoRA**: Weight-Decomposed Low-Rank Adaptation — slightly better accuracy, ~2x slower

## Classes (alphabetical, matching ImageFolder)

- debris
- garbage
- non_civic
- pothole
