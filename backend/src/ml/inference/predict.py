from __future__ import annotations

import logging
from pathlib import Path

import torch
from PIL import Image
from torchvision import transforms

from src.ml.models.build_model import build_model, robust_load_state_dict

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).resolve().parent.parent.parent.parent.parent / "models" / "model.pth"

CLASS_NAMES = ["debris", "garbage", "non_civic", "pothole"]

_model = None
_device = None


def _get_device() -> torch.device:
    global _device
    if _device is None:
        _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return _device


def _get_model():
    global _model
    if _model is not None:
        return _model

    device = _get_device()
    model = build_model(len(CLASS_NAMES))

    if MODEL_PATH.exists():
        logger.info("Loading trained model from %s", MODEL_PATH)
        state_dict = torch.load(str(MODEL_PATH), map_location=device, weights_only=True)
        robust_load_state_dict(model, state_dict)
    else:
        logger.warning("No trained model found at %s — using pretrained ImageNet weights", MODEL_PATH)

    model.to(device)
    model.eval()
    _model = model
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
        "model": "mobilenet_v2",
        "model_path": str(MODEL_PATH),
    }


def get_model_info() -> dict:
    return {
        "model_path": str(MODEL_PATH),
        "model_exists": MODEL_PATH.exists(),
        "model_size_mb": round(MODEL_PATH.stat().st_size / 1024 / 1024, 2) if MODEL_PATH.exists() else 0,
        "classes": CLASS_NAMES,
        "num_classes": len(CLASS_NAMES),
        "device": str(_get_device()),
    }
