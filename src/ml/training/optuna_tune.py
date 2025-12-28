import optuna
import torch
import torch.nn as nn
import torch.optim as optim

from ml.data.dataloader import get_dataloaders
from ml.models.model import build_model
from ml.utils.device import get_device


def objective(trial):
    lr = trial.suggest_float("lr", 1e-4, 1e-2, log=True)
    batch_size = trial.suggest_categorical("batch_size", [16, 32, 64])

    dataloader, classes = get_dataloaders("data/raw", batch_size)
    device = get_device()

    model = build_model(len(classes)).to(device)
    optimizer = optim.Adam(model.classifier[1].parameters(), lr=lr)
    criterion = nn.CrossEntropyLoss()

    model.train()
    total_loss = 0.0

    for images, labels in dataloader:
        images, labels = images.to(device), labels.to(device)
        optimizer.zero_grad()
        loss = criterion(model(images), labels)
        loss.backward()
        optimizer.step()
        total_loss += loss.item()

    return total_loss / len(dataloader)


if __name__ == "__main__":
    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=5)

    print("Best params:", study.best_params)
