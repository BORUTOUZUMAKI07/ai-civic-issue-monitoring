"""PEFT wrappers for MobileNetV2 — LoRA and DoRA adapters.

Applies parameter-efficient fine-tuning to MobileNetV2's depthwise
separable convolution layers, reducing trainable parameters from ~3.4M
to ~50-200K while maintaining accuracy.
"""

from __future__ import annotations

import logging
from pathlib import Path

import torch.nn as nn
from peft import LoraConfig, PeftModel, TaskType, get_peft_model

logger = logging.getLogger(__name__)

# Target the depthwise conv in the last 3 MobileNetV2 inverted residual blocks.
# These are the most task-adaptive layers for classification.
LORA_TARGET_MODULES = [
    "features.14.conv.0",
    "features.15.conv.0",
    "features.16.conv.0",
]


def apply_lora(
    model: nn.Module,
    r: int = 8,
    alpha: int = 16,
    dropout: float = 0.1,
    use_dora: bool = False,
    target_modules: list[str] | None = None,
) -> PeftModel:
    """Apply LoRA or DoRA adapter to MobileNetV2.

    Args:
        model: Base MobileNetV2 model (with classifier head already set).
        r: LoRA rank (higher = more capacity, more params).
        alpha: LoRA alpha scaling factor.
        dropout: LoRA dropout rate.
        use_dora: If True, use DoRA (Weight-Decomposed Low-Rank Adaptation).
        target_modules: Module names to apply LoRA to. Defaults to last 3
            depthwise conv blocks.

    Returns:
        PeftModel with adapters attached.
    """
    if target_modules is None:
        target_modules = LORA_TARGET_MODULES

    config = LoraConfig(
        task_type=TaskType.IMAGE_CLASSIFICATION,
        r=r,
        lora_alpha=alpha,
        lora_dropout=dropout,
        target_modules=target_modules,
        use_dora=use_dora,
        bias="none",
    )

    peft_model = get_peft_model(model, config)
    peft_model.print_trainable_parameters()

    adapter_type = "DoRA" if use_dora else "LoRA"
    logger.info(
        "Applied %s adapter: r=%d, alpha=%d, dropout=%.2f, targets=%s",
        adapter_type,
        r,
        alpha,
        dropout,
        target_modules,
    )

    return peft_model


def merge_adapter(peft_model: PeftModel) -> nn.Module:
    """Merge adapter weights into base model for fast inference.

    Returns a plain nn.Module with no PEFT overhead.
    """
    merged = peft_model.merge_and_unload()
    logger.info("Merged adapter weights into base model")
    return merged


def save_adapter(peft_model: PeftModel, path: str | Path) -> None:
    """Save only adapter weights (typically 1-5MB vs 9MB full model).

    Args:
        peft_model: PeftModel with adapters attached.
        path: Directory to save adapter weights.
    """
    save_path = Path(path)
    save_path.mkdir(parents=True, exist_ok=True)
    peft_model.save_pretrained(str(save_path))

    # Log adapter size
    total_size = sum(f.stat().st_size for f in save_path.rglob("*") if f.is_file())
    logger.info(
        "Saved adapter to %s (%.2f MB)", save_path, total_size / (1024 * 1024)
    )


def load_adapter(
    base_model: nn.Module,
    adapter_path: str | Path,
) -> PeftModel:
    """Load adapter weights onto a base model.

    Args:
        base_model: Base MobileNetV2 model (with classifier head).
        adapter_path: Directory containing adapter weights.

    Returns:
        PeftModel with adapter loaded.
    """
    peft_model = PeftModel.from_pretrained(base_model, str(adapter_path))
    logger.info("Loaded adapter from %s", adapter_path)
    return peft_model
