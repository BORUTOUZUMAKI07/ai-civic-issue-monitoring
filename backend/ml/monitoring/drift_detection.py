from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


class DriftDetector:
    def __init__(self, reference_metrics_path: str, threshold: float = 0.05) -> None:
        self.threshold = threshold
        self.reference = self._load_reference(reference_metrics_path)

    def _load_reference(self, path: str) -> dict[str, Any]:
        with open(path) as f:
            return json.load(f)

    def detect_accuracy_drift(self, current_accuracy: float) -> dict[str, Any]:
        ref_accuracy = self.reference.get("accuracy", 0)
        drift = ref_accuracy - current_accuracy
        has_drift = drift > self.threshold

        result = {
            "metric": "accuracy",
            "reference": ref_accuracy,
            "current": current_accuracy,
            "drift": drift,
            "threshold": self.threshold,
            "has_drift": has_drift,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if has_drift:
            logger.warning(
                "Accuracy drift detected: %.4f -> %.4f (drift: %.4f)",
                ref_accuracy,
                current_accuracy,
                drift,
            )

        return result

    def detect_distribution_drift(
        self, current_predictions: list[int], reference_distribution: dict[int, float] | None = None
    ) -> dict[str, Any]:
        if reference_distribution is None:
            reference_distribution = self.reference.get("distribution", {})

        current_counts = np.bincount(current_predictions)
        current_dist = current_counts / current_counts.sum()

        kl_divergence = 0.0
        for idx, ref_prob in reference_distribution.items():
            idx = int(idx)
            cur_prob = current_dist[idx] if idx < len(current_dist) else 0
            if ref_prob > 0 and cur_prob > 0:
                kl_divergence += ref_prob * np.log(ref_prob / cur_prob)

        has_drift = kl_divergence > self.threshold

        return {
            "metric": "distribution",
            "kl_divergence": float(kl_divergence),
            "threshold": self.threshold,
            "has_drift": has_drift,
            "current_distribution": current_dist.tolist(),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def save_drift_report(self, report: dict[str, Any], output_dir: str) -> str:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filepath = output / f"drift_report_{timestamp}.json"
        with open(filepath, "w") as f:
            json.dump(report, f, indent=2)
        logger.info("Drift report saved to %s", filepath)
        return str(filepath)
