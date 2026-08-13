"""
A/B Testing for ML Models — Shadow Deployment + Traffic Splitting.

Champion = current production model (model.pth / model.onnx)
Challenger = new candidate model (model_challenger.pth / model_challenger.onnx)

Two modes:
  1. Shadow mode: Run both models, log both predictions, only use champion's result
  2. Traffic split: Route X% of traffic to challenger, rest to champion
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODELS_DIR = PROJECT_ROOT / "models"

CHAMPION_PATH = MODELS_DIR / "model.pth"
CHAMPION_ONNX = MODELS_DIR / "model.onnx"
CHALLENGER_PATH = MODELS_DIR / "model_challenger.pth"
CHALLENGER_ONNX = MODELS_DIR / "model_challenger.onnx"

CLASS_NAMES = ["debris", "garbage", "non_civic", "pothole"]


@dataclass
class ABTestConfig:
    enabled: bool = False
    mode: str = "shadow"  # "shadow" or "traffic_split"
    traffic_pct: float = 0.1  # 10% to challenger in traffic_split mode
    log_to_db: bool = True


@dataclass
class PredictionResult:
    label: str
    confidence: float
    probabilities: dict
    model_version: str  # "champion" or "challenger"
    inference_time_ms: float
    model_type: str  # "onnx" or "pytorch"


@dataclass
class ABTestResult:
    champion: PredictionResult
    challenger: Optional[PredictionResult] = None
    chosen: str = "champion"  # which model's prediction was used
    is_shadow: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ABTestPredictor:
    """Manages A/B testing between champion and challenger models."""

    def __init__(self, config: ABTestConfig | None = None):
        self.config = config or ABTestConfig()
        self._champion_session = None
        self._challenger_session = None
        self._champion_model = None
        self._challenger_model = None
        self._stats = {"champion": 0, "challenger": 0, "total": 0}

    def _get_onnx_session(self, model_path: Path):
        """Load an ONNX model session."""
        if not model_path.exists():
            return None
        try:
            import onnxruntime as ort

            opts = ort.SessionOptions()
            opts.inter_op_num_threads = 2
            opts.intra_op_num_threads = 2
            opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            return ort.InferenceSession(str(model_path), opts)
        except Exception as e:
            logger.warning("Failed to load ONNX from %s: %s", model_path, e)
            return None

    def _preprocess(self, image: Image.Image) -> np.ndarray:
        """Convert PIL image to normalized numpy array."""
        img = image.convert("RGB").resize((224, 224))
        arr = np.array(img, dtype=np.float32) / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
        std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
        arr = (arr - mean) / std
        arr = arr.transpose(2, 0, 1)
        return np.expand_dims(arr, axis=0)

    def _infer_onnx(self, session, image: Image.Image, model_version: str) -> PredictionResult:
        """Run inference via ONNX Runtime."""
        input_data = self._preprocess(image)
        start = time.perf_counter()
        outputs = session.run(None, {"input": input_data})
        elapsed_ms = (time.perf_counter() - start) * 1000

        logits = outputs[0]
        exp_logits = np.exp(logits - np.max(logits, axis=1, keepdims=True))
        probs = exp_logits / np.sum(exp_logits, axis=1, keepdims=True)
        pred_idx = int(np.argmax(probs, axis=1)[0])

        return PredictionResult(
            label=CLASS_NAMES[pred_idx],
            confidence=round(float(probs[0][pred_idx]), 4),
            probabilities={CLASS_NAMES[i]: round(float(probs[0][i]), 4) for i in range(len(CLASS_NAMES))},
            model_version=model_version,
            inference_time_ms=round(elapsed_ms, 2),
            model_type="onnx",
        )

    def _infer_pytorch(self, model, image: Image.Image, model_version: str) -> PredictionResult:
        """Run inference via PyTorch."""
        import torch
        from torchvision import transforms

        transform = transforms.Compose(
            [
                transforms.Resize((224, 224)),
                transforms.Lambda(lambda img: img.convert("RGB")),
                transforms.ToTensor(),
                transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
            ]
        )

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        img_tensor = transform(image).unsqueeze(0).to(device)

        start = time.perf_counter()
        with torch.no_grad():
            outputs = model(img_tensor)
            probs = torch.softmax(outputs, dim=1)
        elapsed_ms = (time.perf_counter() - start) * 1000

        confidence, pred_idx = torch.max(probs, dim=1)

        return PredictionResult(
            label=CLASS_NAMES[int(pred_idx.item())],
            confidence=round(confidence.item(), 4),
            probabilities={CLASS_NAMES[i]: round(probs[0][i].item(), 4) for i in range(len(CLASS_NAMES))},
            model_version=model_version,
            inference_time_ms=round(elapsed_ms, 2),
            model_type="pytorch",
        )

    def predict(self, image: Image.Image) -> ABTestResult:
        """Run A/B test prediction.

        Returns ABTestResult with champion (always), challenger (if enabled),
        and which model was chosen for the final response.
        """
        if not self.config.enabled:
            champion = self._predict_champion(image)
            return ABTestResult(champion=champion, chosen="champion")

        champion = self._predict_champion(image)

        challenger = None
        if CHALLENGER_ONNX.exists() or CHALLENGER_PATH.exists():
            challenger = self._predict_challenger(image)

        if self.config.mode == "shadow":
            self._stats["total"] += 1
            self._stats["champion"] += 1
            return ABTestResult(
                champion=champion,
                challenger=challenger,
                chosen="champion",
                is_shadow=True,
            )

        if self.config.mode == "traffic_split" and challenger is not None:
            self._stats["total"] += 1
            if random.random() < self.config.traffic_pct:
                self._stats["challenger"] += 1
                return ABTestResult(
                    champion=champion,
                    challenger=challenger,
                    chosen="challenger",
                    is_shadow=False,
                )
            else:
                self._stats["champion"] += 1
                return ABTestResult(
                    champion=champion,
                    challenger=challenger,
                    chosen="champion",
                    is_shadow=False,
                )

        return ABTestResult(champion=champion, chosen="champion")

    def _predict_champion(self, image: Image.Image) -> PredictionResult:
        """Run inference on champion model."""
        session = self._get_onnx_session(CHAMPION_ONNX)
        if session:
            return self._infer_onnx(session, image, "champion")

        model = self._load_pytorch(CHAMPION_PATH, "champion")
        if model:
            return self._infer_pytorch(model, image, "champion")

        raise RuntimeError("No champion model found")

    def _predict_challenger(self, image: Image.Image) -> PredictionResult:
        """Run inference on challenger model."""
        session = self._get_onnx_session(CHALLENGER_ONNX)
        if session:
            return self._infer_onnx(session, image, "challenger")

        model = self._load_pytorch(CHALLENGER_PATH, "challenger")
        if model:
            return self._infer_pytorch(model, image, "challenger")

        return None

    def _load_pytorch(self, path: Path, version: str):
        """Load a PyTorch model from path."""
        if not path.exists():
            return None
        try:
            import torch

            from src.ml.models.build_model import build_model, robust_load_state_dict

            model = build_model(len(CLASS_NAMES))
            state_dict = torch.load(str(path), map_location="cpu", weights_only=True)
            robust_load_state_dict(model, state_dict)
            model.eval()
            return model
        except Exception as e:
            logger.warning("Failed to load PyTorch model %s: %s", path, e)
            return None

    def get_stats(self) -> dict:
        """Get A/B test traffic statistics."""
        total = self._stats["total"]
        return {
            "enabled": self.config.enabled,
            "mode": self.config.mode,
            "traffic_pct": self.config.traffic_pct,
            "total_requests": total,
            "champion_count": self._stats["champion"],
            "challenger_count": self._stats["challenger"],
            "champion_pct": round(self._stats["champion"] / total * 100, 1) if total else 0,
            "challenger_pct": round(self._stats["challenger"] / total * 100, 1) if total else 0,
            "challenger_model_exists": CHALLENGER_ONNX.exists() or CHALLENGER_PATH.exists(),
        }


_ab_tester: ABTestPredictor | None = None


def get_ab_tester() -> ABTestPredictor:
    """Get or create the singleton A/B test predictor."""
    global _ab_tester
    if _ab_tester is None:
        from src.core.config import settings

        config = ABTestConfig(
            enabled=getattr(settings, "AB_TEST_ENABLED", False),
            mode=getattr(settings, "AB_TEST_MODE", "shadow"),
            traffic_pct=getattr(settings, "AB_TEST_TRAFFIC_PCT", 0.1),
        )
        _ab_tester = ABTestPredictor(config)
    return _ab_tester
