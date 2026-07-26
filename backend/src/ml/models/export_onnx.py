"""Export trained MobileNetV2 to ONNX format for faster CPU inference."""

from __future__ import annotations

import logging
from pathlib import Path

import torch

from src.ml.models.build_model import build_model, robust_load_state_dict

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
MODEL_PATH = PROJECT_ROOT / "models" / "model.pth"
ONNX_PATH = PROJECT_ROOT / "models" / "model.onnx"


def export_to_onnx(
    num_classes: int = 4,
    output_path: Path | str | None = None,
    opset: int = 17,
) -> Path:
    """Export trained MobileNetV2 to ONNX format.

    Returns path to the exported ONNX model.
    """
    output_path = Path(output_path) if output_path else ONNX_PATH

    device = torch.device("cpu")
    model = build_model(num_classes)

    if MODEL_PATH.exists():
        logger.info("Loading trained weights from %s", MODEL_PATH)
        state_dict = torch.load(str(MODEL_PATH), map_location=device, weights_only=True)
        robust_load_state_dict(model, state_dict)
    else:
        logger.warning("No trained model found, exporting with pretrained weights")

    model.to(device)
    model.eval()

    dummy_input = torch.randn(1, 3, 224, 224, device=device)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    torch.onnx.export(
        model,
        dummy_input,
        str(output_path),
        opset_version=opset,
        input_names=["input"],
        output_names=["output"],
        dynamo=False,
    )

    size_mb = output_path.stat().st_size / 1024 / 1024
    logger.info("Exported ONNX model to %s (%.2f MB)", output_path, size_mb)
    print(f"ONNX model exported: {output_path} ({size_mb:.2f} MB)")
    return output_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    export_to_onnx()
