from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
import torch.nn as nn
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

from ml.training.train import CIVIC_CATEGORIES, build_model

logger = logging.getLogger(__name__)


class ModelEvaluator:
    def __init__(self, model_path: str, device: str | None = None) -> None:
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self.model = self._load_model(model_path)

    def _load_model(self, model_path: str) -> nn.Module:
        checkpoint = torch.load(model_path, map_location=self.device, weights_only=False)
        num_classes = checkpoint.get("num_classes", len(CIVIC_CATEGORIES))
        model = build_model(num_classes)
        model.load_state_dict(checkpoint["model_state_dict"])
        model.to(self.device)
        model.eval()
        return model

    def evaluate(self, dataloader: Any) -> dict[str, Any]:
        all_preds: list[int] = []
        all_labels: list[int] = []

        with torch.no_grad():
            for images, labels in dataloader:
                images = images.to(self.device)
                outputs = self.model(images)
                _, predicted = torch.max(outputs, 1)
                all_preds.extend(predicted.cpu().numpy().tolist())
                all_labels.extend(labels.numpy().tolist())

        accuracy = accuracy_score(all_labels, all_preds)
        f1_macro = f1_score(all_labels, all_preds, average="macro", zero_division=0)
        f1_weighted = f1_score(all_labels, all_preds, average="weighted", zero_division=0)
        precision = precision_score(all_labels, all_preds, average="macro", zero_division=0)
        recall = recall_score(all_labels, all_preds, average="macro", zero_division=0)
        cm = confusion_matrix(all_labels, all_preds).tolist()
        report = classification_report(
            all_labels,
            all_preds,
            target_names=CIVIC_CATEGORIES[: len(set(all_labels))],
            zero_division=0,
            output_dict=True,
        )

        results = {
            "accuracy": accuracy,
            "f1_macro": f1_macro,
            "f1_weighted": f1_weighted,
            "precision_macro": precision,
            "recall_macro": recall,
            "confusion_matrix": cm,
            "classification_report": report,
            "num_samples": len(all_labels),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        logger.info("Evaluation: accuracy=%.4f, f1_macro=%.4f", accuracy, f1_macro)
        return results

    def save_report(self, results: dict[str, Any], output_path: str) -> None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w") as f:
            json.dump(results, f, indent=2)
        logger.info("Evaluation report saved to %s", output_path)
