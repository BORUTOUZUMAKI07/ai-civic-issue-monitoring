"""Training pipeline for CivicPulse issue classifier.

Uses MobileNetV2 with transfer learning.
Logs experiments to DagsHub MLflow.
Tracks hyperparameters with Optuna.
"""

import os
import sys
from pathlib import Path

import mlflow
import mlflow.pytorch
import optuna
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import datasets, models, transforms

# Configuration
NUM_CLASSES = 4
CLASS_NAMES = ["debris", "garbage", "non_civic", "pothole"]
EPOCHS = 20
BATCH_SIZE = 32
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# DagsHub MLflow config
MLFLOW_TRACKING_URI = os.getenv(
    "MLFLOW_TRACKING_URI", "https://dagshub.com/ram.atchutratna/ai-civic-issue-monitoring.mlflow"
)
MLFLOW_USERNAME = os.getenv("MLFLOW_TRACKING_USERNAME", "")
MLFLOW_PASSWORD = os.getenv("MLFLOW_TRACKING_PASSWORD", "")


def build_model(num_classes: int, unfreeze_last_n: int = 0):
    """Build MobileNetV2 for transfer learning."""
    model = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.DEFAULT)

    if unfreeze_last_n > 0:
        for param in model.parameters():
            param.requires_grad = False
        num_blocks = len(model.features)
        start_index = max(0, num_blocks - unfreeze_last_n)
        for i in range(start_index, num_blocks):
            for param in model.features[i].parameters():
                param.requires_grad = True
    else:
        for param in model.parameters():
            param.requires_grad = False

    model.classifier[1] = nn.Linear(model.last_channel, num_classes)
    return model


def get_dataloaders(data_path: str, batch_size: int):
    """Load training data from balanced_gold directory."""
    train_dir = Path(data_path) / "train"
    val_dir = Path(data_path) / "val"

    train_transform = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.RandomHorizontalFlip(),
            transforms.RandomRotation(15),
            transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )

    val_transform = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ]
    )

    train_dataset = datasets.ImageFolder(str(train_dir), transform=train_transform)
    val_dataset = datasets.ImageFolder(str(val_dir), transform=val_transform)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False, num_workers=0)

    return train_loader, val_loader, train_dataset.classes


def train_one_epoch(model, loader, criterion, optimizer, device):
    """Train for one epoch."""
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


def validate(model, loader, criterion, device):
    """Validate the model."""
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


def objective(trial: optuna.Trial):
    """Optuna objective function."""
    lr = trial.suggest_float("lr", 1e-4, 1e-2, log=True)
    batch_size = trial.suggest_categorical("batch_size", [16, 32, 64])
    unfreeze_last_n = trial.suggest_int("unfreeze_last_n", 1, 10)

    data_path = os.getenv("DATA_PATH", "data/balanced_gold")
    if not Path(data_path).exists():
        print(f"Data path not found: {data_path}")
        return float("inf")

    train_loader, val_loader, classes = get_dataloaders(data_path, batch_size)

    model = build_model(len(classes), unfreeze_last_n).to(DEVICE)
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(filter(lambda p: p.requires_grad, model.parameters()), lr=lr)

    model.train()
    total_loss = 0.0
    for images, labels in train_loader:
        images, labels = images.to(DEVICE), labels.to(DEVICE)
        optimizer.zero_grad()
        loss = criterion(model(images), labels)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()

    return total_loss / len(train_loader)


def main():
    """Main training function with MLflow tracking."""
    # Set up MLflow
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("civicpulse-mobilenetv2")

    print(f"MLflow tracking URI: {MLFLOW_TRACKING_URI}")
    print(f"MLflow username: {MLFLOW_USERNAME}")

    # Check data exists
    data_path = os.getenv("DATA_PATH", "data/balanced_gold")
    if not Path(data_path).exists():
        print(f"ERROR: Data path not found: {data_path}")
        print("Please run: dvc pull -r origin")
        sys.exit(1)

    # Run Optuna for hyperparameter tuning
    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=5)

    best_params = study.best_params
    print(f"Best params: {best_params}")

    # Train final model with best params
    train_loader, val_loader, classes = get_dataloaders(data_path, best_params.get("batch_size", 32))

    model = build_model(len(classes), best_params.get("unfreeze_last_n", 5)).to(DEVICE)

    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(filter(lambda p: p.requires_grad, model.parameters()), lr=best_params.get("lr", 0.001))

    # Log to MLflow
    with mlflow.start_run():
        mlflow.log_params(best_params)
        mlflow.log_param("num_classes", len(classes))
        mlflow.log_param("class_names", str(classes))
        mlflow.log_param("model", "mobilenet_v2")

        best_val_acc = 0.0
        for epoch in range(EPOCHS):
            train_loss, train_acc = train_one_epoch(model, train_loader, criterion, optimizer, DEVICE)
            val_loss, val_acc = validate(model, val_loader, criterion, DEVICE)

            mlflow.log_metrics(
                {
                    "train_loss": train_loss,
                    "train_acc": train_acc,
                    "val_loss": val_loss,
                    "val_acc": val_acc,
                },
                step=epoch,
            )

            print(
                f"Epoch {epoch + 1}/{EPOCHS}: "
                f"train_loss={train_loss:.4f}, train_acc={train_acc:.4f}, "
                f"val_loss={val_loss:.4f}, val_acc={val_acc:.4f}"
            )

            if val_acc > best_val_acc:
                best_val_acc = val_acc
                mlflow.pytorch.log_model(model, "model")

        mlflow.log_metric("best_val_acc", best_val_acc)

    # Save model locally
    model_path = Path("models/model.pth")
    model_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(model.state_dict(), str(model_path))
    print(f"Model saved to {model_path}")


if __name__ == "__main__":
    main()
