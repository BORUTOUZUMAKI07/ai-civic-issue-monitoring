from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms

logger = logging.getLogger(__name__)

CIVIC_CATEGORIES = [
    "pothole",
    "garbage",
    "streetlight",
    "waterlogging",
    "encroachment",
    "road_damage",
    "drainage",
    "noise",
    "air_quality",
    "public_transport",
    "other",
]
NUM_CLASSES = len(CIVIC_CATEGORIES)


def build_model(num_classes: int = NUM_CLASSES) -> nn.Module:
    model = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.DEFAULT)
    model.classifier[1] = nn.Linear(model.last_channel, num_classes)
    return model


class CivicDataset(Dataset):
    def __init__(self, data_dir: str, transform: transforms.Compose | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.transform = transform or transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])
        self.samples: list[tuple[Path, int]] = []
        self._load_samples()

    def _load_samples(self) -> None:
        for idx, category in enumerate(CIVIC_CATEGORIES):
            category_dir = self.data_dir / category
            if not category_dir.exists():
                continue
            for img_path in category_dir.glob("*.jpg"):
                self.samples.append((img_path, idx))
            for img_path in category_dir.glob("*.png"):
                self.samples.append((img_path, idx))

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, int]:
        from PIL import Image

        img_path, label = self.samples[idx]
        image = Image.open(img_path).convert("RGB")
        if self.transform:
            image = self.transform(image)
        return image, label


def train_model(
    data_dir: str,
    output_path: str,
    epochs: int = 20,
    batch_size: int = 32,
    learning_rate: float = 1e-4,
    device: str | None = None,
) -> dict[str, float]:
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    model = build_model().to(device)
    dataset = CivicDataset(data_dir)

    if len(dataset) == 0:
        raise ValueError(f"No training samples found in {data_dir}")

    train_size = int(0.8 * len(dataset))
    val_size = len(dataset) - train_size
    train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_size, val_size])

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=learning_rate)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=3, factor=0.5)

    best_val_acc = 0.0
    history: dict[str, list[float]] = {"train_loss": [], "val_loss": [], "val_acc": []}

    for epoch in range(epochs):
        model.train()
        train_loss = 0.0
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * images.size(0)

        model.eval()
        val_loss = 0.0
        correct = 0
        total = 0
        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                outputs = model(images)
                loss = criterion(outputs, labels)
                val_loss += loss.item() * images.size(0)
                _, predicted = torch.max(outputs, 1)
                total += labels.size(0)
                correct += (predicted == labels).sum().item()

        avg_train_loss = train_loss / train_size
        avg_val_loss = val_loss / val_size
        val_acc = correct / total

        history["train_loss"].append(avg_train_loss)
        history["val_loss"].append(avg_val_loss)
        history["val_acc"].append(val_acc)

        scheduler.step(avg_val_loss)

        logger.info(
            "Epoch %d/%d - train_loss: %.4f, val_loss: %.4f, val_acc: %.4f",
            epoch + 1,
            epochs,
            avg_train_loss,
            avg_val_loss,
            val_acc,
        )

        if val_acc > best_val_acc:
            best_val_acc = val_acc
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            torch.save(
                {
                    "model_state_dict": model.state_dict(),
                    "num_classes": NUM_CLASSES,
                    "categories": CIVIC_CATEGORIES,
                    "val_acc": val_acc,
                    "epoch": epoch,
                },
                str(output),
            )

    metrics = {
        "best_val_acc": best_val_acc,
        "final_train_loss": history["train_loss"][-1] if history["train_loss"] else 0,
        "final_val_loss": history["val_loss"][-1] if history["val_loss"] else 0,
        "epochs": epochs,
    }

    metrics_path = Path(output_path).with_suffix(".metrics.json")
    with open(metrics_path, "w") as f:
        json.dump(
            {**metrics, "history": history, "timestamp": datetime.now(timezone.utc).isoformat()},
            f,
            indent=2,
        )

    logger.info("Training complete. Best val_acc: %.4f. Saved to %s", best_val_acc, output_path)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Train CivicPulse classification model")
    parser.add_argument("--data-dir", default="data/training", help="Training data directory")
    parser.add_argument("--output", default="models/model_phase1.pth", help="Output model path")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-4)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    train_model(args.data_dir, args.output, args.epochs, args.batch_size, args.lr)


if __name__ == "__main__":
    main()
