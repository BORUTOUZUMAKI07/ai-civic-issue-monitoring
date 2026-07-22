from __future__ import annotations

import logging
from pathlib import Path

import torch
from PIL import Image
from torchvision import transforms

from src.ml.models.build_model import build_model, robust_load_state_dict

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
MODEL_PATH = PROJECT_ROOT / "models" / "model.pth"
ADAPTER_DIR = PROJECT_ROOT / "models" / "adapter"

CLASS_NAMES = ["debris", "garbage", "non_civic", "pothole"]

_model = None
_device = None
_model_type = None  # "peft" or "standard"


def _get_device() -> torch.device:
    global _device
    if _device is None:
        _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return _device


def _get_model():
    global _model, _model_type
    if _model is not None:
        return _model

    device = _get_device()

    # Prefer PEFT adapter if available
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
        _model_type = "standard"

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


def predict_issue(image: Image.Image) -> dict:
    """Run real MobileNetV2 inference on an image.

    Returns {"label": str, "confidence": float, "probabilities": dict}.
    """
    model = _get_model()
    device = _get_device()

    img_tensor = _transform(image).unsqueeze(0).to(device)

    with torch.no_grad():
        outputs = model(img_tensor)
        probs = torch.softmax(outputs, dim=1)

    confidence, pred_idx = torch.max(probs, dim=1)
    label = CLASS_NAMES[int(pred_idx.item())]
    conf_val = round(confidence.item(), 4)

    all_probs = {CLASS_NAMES[i]: round(probs[0][i].item(), 4) for i in range(len(CLASS_NAMES))}

    return {
        "label": label,
        "confidence": conf_val,
        "probabilities": all_probs,
        "model": f"mobilenet_v2_{_model_type or 'unknown'}",
        "model_path": str(MODEL_PATH),
        "adapter_path": str(ADAPTER_DIR) if ADAPTER_DIR.exists() else None,
    }


def get_model_info() -> dict:
    adapter_exists = ADAPTER_DIR.exists() and any(ADAPTER_DIR.iterdir())
    adapter_size = 0
    if adapter_exists:
        adapter_size = sum(f.stat().st_size for f in ADAPTER_DIR.rglob("*") if f.is_file())

    return {
        "model_path": str(MODEL_PATH),
        "model_exists": MODEL_PATH.exists(),
        "model_size_mb": round(MODEL_PATH.stat().st_size / 1024 / 1024, 2) if MODEL_PATH.exists() else 0,
        "model_type": _model_type or "not_loaded",
        "adapter_exists": adapter_exists,
        "adapter_size_mb": round(adapter_size / 1024 / 1024, 2) if adapter_size else 0,
        "classes": CLASS_NAMES,
        "num_classes": len(CLASS_NAMES),
        "device": str(_get_device()),
    }
