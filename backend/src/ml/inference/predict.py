from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image
from torchvision import transforms

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
ADAPTER_DIR = PROJECT_ROOT / "models" / "adapter"
ONNX_PATH = PROJECT_ROOT / "models" / "model.onnx"
CLASS_NAMES_PATH = PROJECT_ROOT / "configs" / "class_names.json"


def _get_model_path() -> Path:
    from src.core.config import settings

    p = Path(settings.MODEL_PATH)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p


MODEL_PATH = _get_model_path()


def _load_class_names() -> list[str]:
    """Load class names from config file, falling back to hardcoded default."""
    if CLASS_NAMES_PATH.exists():
        with open(CLASS_NAMES_PATH) as f:
            names = json.load(f)
        if isinstance(names, list) and names:
            return names
    return ["debris", "garbage", "non_civic", "pothole"]


CLASS_NAMES = _load_class_names()

_model = None
_device = None
_model_type = None
_session = None


def _get_device():
    global _device
    if _device is None:
        import torch

        _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return _device


def _get_onnx_session():
    global _session, _model_type
    if _session is not None:
        return _session

    if not ONNX_PATH.exists():
        return None

    try:
        import onnxruntime as ort

        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 2
        opts.intra_op_num_threads = 2
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _session = ort.InferenceSession(str(ONNX_PATH), opts)
        _model_type = "onnx"
        logger.info("Loaded ONNX model from %s", ONNX_PATH)
        return _session
    except Exception as e:
        logger.warning("Failed to load ONNX model: %s", e)
        return None


def _get_torch_model():
    global _model, _model_type
    if _model is not None:
        return _model

    import torch

    from src.ml.models.build_model import build_model, robust_load_state_dict

    device = _get_device()

    if ADAPTER_DIR.exists() and any(ADAPTER_DIR.iterdir()):
        logger.info("Loading PEFT adapter from %s", ADAPTER_DIR)
        from peft import PeftModel

        base_model = build_model(len(CLASS_NAMES))
        peft_model = PeftModel.from_pretrained(base_model, str(ADAPTER_DIR))
        _model = peft_model.merge_and_unload()
        _model_type = "peft_merged"
        logger.info("Loaded PEFT adapter and merged into base model")

    elif MODEL_PATH.exists():
        logger.info("Loading standard model from %s", MODEL_PATH)
        _model = build_model(len(CLASS_NAMES))
        state_dict = torch.load(str(MODEL_PATH), map_location=device, weights_only=True)
        robust_load_state_dict(_model, state_dict)
        _model_type = "pytorch"

    else:
        logger.warning("No model found — using pretrained ImageNet weights")
        _model = build_model(len(CLASS_NAMES))
        _model_type = "pretrained"

    _model.to(device)
    _model.eval()
    return _model


_transform = transforms.Compose(
    [
        transforms.Resize((224, 224)),
        transforms.Lambda(lambda img: img.convert("RGB")),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ]
)


def _preprocess(image: Image.Image) -> np.ndarray:
    """Convert PIL image to normalized numpy array for ONNX."""
    img = image.convert("RGB").resize((224, 224))
    arr = np.array(img, dtype=np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    arr = (arr - mean) / std
    arr = arr.transpose(2, 0, 1)
    return np.expand_dims(arr, axis=0)


def predict_issue(image: Image.Image) -> dict:
    """Run inference on an image.

    Prefers ONNX Runtime (faster on CPU), falls back to PyTorch.
    Logs prediction to MongoDB for drift detection.

    Returns {"label": str, "confidence": float, "probabilities": dict}.
    """
    start_time = time.perf_counter()
    session = _get_onnx_session()

    if session is not None:
        input_data = _preprocess(image)
        outputs = session.run(None, {"input": input_data})
        logits = outputs[0]

        exp_logits = np.exp(logits - np.max(logits, axis=1, keepdims=True))
        probs = exp_logits / np.sum(exp_logits, axis=1, keepdims=True)

        pred_idx = int(np.argmax(probs, axis=1)[0])
        confidence = float(probs[0][pred_idx])
        all_probs = {CLASS_NAMES[i]: round(float(probs[0][i]), 4) for i in range(len(CLASS_NAMES))}
        model_type = "onnx"
        model_path = str(ONNX_PATH)
    else:
        import torch

        model = _get_torch_model()
        device = _get_device()
        img_tensor = _transform(image).unsqueeze(0).to(device)

        with torch.no_grad():
            outputs = model(img_tensor)
            probs = torch.softmax(outputs, dim=1)

        confidence, pred_idx = torch.max(probs, dim=1)
        all_probs = {CLASS_NAMES[i]: round(probs[0][i].item(), 4) for i in range(len(CLASS_NAMES))}
        model_type = _model_type or "pytorch"
        model_path = str(MODEL_PATH)

    elapsed_ms = (time.perf_counter() - start_time) * 1000
    label = CLASS_NAMES[pred_idx] if isinstance(pred_idx, int) else CLASS_NAMES[int(pred_idx)]

    result = {
        "label": label,
        "confidence": round(confidence, 4) if isinstance(confidence, float) else round(float(confidence), 4),
        "probabilities": all_probs,
        "model": f"mobilenet_v2_{model_type}",
        "model_path": model_path,
        "adapter_path": str(ADAPTER_DIR) if ADAPTER_DIR.exists() else None,
        "inference_time_ms": round(elapsed_ms, 2),
    }

    _log_prediction_for_drift(result)
    return result


_MONGO_CLIENT: "object | None" = None
_MONGO_LOCK = threading.Lock()


def _get_mongo_client():
    """Return a lazily-created, process-wide MongoClient (reused across predictions).

    A single client is shared instead of creating one per prediction, and the server
    selection timeout is kept short so an unreachable MongoDB never blocks inference.
    """
    global _MONGO_CLIENT
    if _MONGO_CLIENT is not None:
        return _MONGO_CLIENT
    with _MONGO_LOCK:
        if _MONGO_CLIENT is None:
            from pymongo import MongoClient

            from src.core.config import settings

            _MONGO_CLIENT = MongoClient(
                settings.MONGODB_URI,
                serverSelectionTimeoutMS=1500,
                connectTimeoutMS=1500,
            )
        return _MONGO_CLIENT


def _log_prediction_for_drift(result: dict):
    """Log prediction to MongoDB for drift detection (non-blocking, fire-and-forget)."""
    record = {
        "predicted_label": result["label"],
        "confidence": result["confidence"],
        "probabilities": result["probabilities"],
        "model": result["model"],
        "inference_time_ms": result["inference_time_ms"],
        "created_at": datetime.now(timezone.utc),
    }

    def _write():
        try:
            client = _get_mongo_client()
            db = client[_get_mongo_db()]
            db["predictions"].insert_one(record)
        except Exception as e:
            logger.debug("Drift logging failed (non-fatal): %s", e)

    threading.Thread(target=_write, daemon=True).start()


def _get_mongo_db():
    from src.core.config import settings

    return settings.MONGODB_DB


def get_model_info() -> dict:
    onnx_exists = ONNX_PATH.exists()
    onnx_size = ONNX_PATH.stat().st_size / 1024 / 1024 if onnx_exists else 0

    adapter_exists = ADAPTER_DIR.exists() and any(ADAPTER_DIR.iterdir())
    adapter_size = 0
    if adapter_exists:
        adapter_size = sum(f.stat().st_size for f in ADAPTER_DIR.rglob("*") if f.is_file())

    return {
        "model_path": str(MODEL_PATH),
        "model_exists": MODEL_PATH.exists(),
        "model_size_mb": round(MODEL_PATH.stat().st_size / 1024 / 1024, 2) if MODEL_PATH.exists() else 0,
        "onnx_path": str(ONNX_PATH),
        "onnx_exists": onnx_exists,
        "onnx_size_mb": round(onnx_size, 2),
        "model_type": _model_type or "not_loaded",
        "adapter_exists": adapter_exists,
        "adapter_size_mb": round(adapter_size / 1024 / 1024, 2) if adapter_size else 0,
        "classes": CLASS_NAMES,
        "num_classes": len(CLASS_NAMES),
        "device": str(_get_device()),
    }
