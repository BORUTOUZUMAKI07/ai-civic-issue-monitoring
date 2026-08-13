"""PEFT wrappers for MobileNetV2.

Applies parameter-efficient fine-tuning to MobileNetV2's depthwise
separable convolution layers, reducing trainable parameters from ~3.4M
to ~2-95K while maintaining accuracy. Supports multiple adaptation
methods (LoRA, DoRA, rsLoRA, AdaLoRA, IA3, OFT, BOFT, LoHa, LoKr) plus
the LoRA+ two-LR and LoRA-FA frozen-A variants.
"""

from __future__ import annotations

import logging
from pathlib import Path

import torch.nn as nn
from peft import (
    AdaLoraConfig,
    BOFTConfig,
    IA3Config,
    LoHaConfig,
    LoKrConfig,
    LoraConfig,
    OFTConfig,
    PeftModel,
    get_peft_model,
)

logger = logging.getLogger(__name__)

# Target the 1x1 pointwise convs in the last 3 MobileNetV2 inverted residual
# blocks. These are the most task-adaptive layers for classification, and
# unlike the depthwise convs (groups == channels) they support arbitrary LoRA
# rank. Each `features.N.conv` is a Sequential whose index 2 is the pointwise
# Conv2d (followed by BatchNorm at index 3).
LORA_TARGET_MODULES = [
    "features.14.conv.2",
    "features.15.conv.2",
    "features.16.conv.2",
]

SUPPORTED_METHODS = [
    "lora",
    "dora",
    "rslora",
    "lora_fa",
    "lora_plus",
    "dora_plus",
    "adalora",
    "ia3",
    "oft",
    "boft",
    "loha",
    "lokr",
]

# Methods whose weights are a low-rank (r, alpha) pair.
RANK_METHODS = frozenset({"lora", "dora", "rslora", "lora_fa", "lora_plus", "dora_plus", "adalora", "loha", "lokr"})

# Methods that implement the LoRA+ two-learning-rate optimizer scheme.
PLUS_METHODS = frozenset({"lora_plus", "dora_plus"})


def apply_peft(
    model: nn.Module,
    method: str = "lora",
    r: int = 8,
    alpha: int = 16,
    dropout: float = 0.1,
    total_step: int = 300,
    target_modules: list[str] | None = None,
) -> PeftModel:
    """Apply a PEFT adapter to MobileNetV2.

    Args:
        model: Base MobileNetV2 model (with classifier head already set).
        method: Adaptation method, one of SUPPORTED_METHODS.
        r: Rank (LoRA-family, AdaLoRA, LoHa, LoKr) or OFT block size.
        alpha: Alpha scaling factor (LoRA-family, LoHa, LoKr).
        dropout: Adapter dropout (LoRA-family, AdaLoRA).
        total_step: Total training steps (AdaLoRA rank scheduler).
        target_modules: Module names to adapt. Defaults to the 1x1 pointwise
            convs in the last 3 inverted residual blocks.

    Returns:
        PeftModel with adapters attached.
    """
    if target_modules is None:
        target_modules = LORA_TARGET_MODULES

    if method not in SUPPORTED_METHODS:
        raise ValueError(f"Unsupported PEFT method {method!r}; choose from {SUPPORTED_METHODS}")

    # No task_type: MobileNetV2 is a plain torchvision CNN (not a transformers
    # model), so `get_peft_model` returns a pass-through `PeftModel`. Setting a
    # transformers-style task_type would dispatch to a wrapper that passes
    # `input_ids` and breaks the forward pass.
    if method in ("lora", "dora", "rslora", "lora_fa", "lora_plus", "dora_plus"):
        config = LoraConfig(
            r=r,
            lora_alpha=alpha,
            lora_dropout=dropout,
            target_modules=target_modules,
            bias="none",
            use_dora=method in ("dora", "dora_plus"),
            use_rslora=(method == "rslora"),
        )
    elif method == "adalora":
        config = AdaLoraConfig(
            r=r,
            lora_alpha=alpha,
            lora_dropout=dropout,
            total_step=total_step,
            target_modules=target_modules,
            bias="none",
        )
    elif method == "ia3":
        config = IA3Config(
            target_modules=target_modules,
            feedforward_modules=target_modules,
        )
    elif method == "oft":
        config = OFTConfig(
            oft_block_size=r,
            target_modules=target_modules,
        )
    elif method == "boft":
        config = BOFTConfig(
            boft_block_size=8,
            boft_n_butterfly_factor=2,
            target_modules=target_modules,
        )
    elif method == "loha":
        config = LoHaConfig(r=r, alpha=alpha, target_modules=target_modules)
    elif method == "lokr":
        config = LoKrConfig(r=r, alpha=alpha, target_modules=target_modules)
    else:  # pragma: no cover - guarded by SUPPORTED_METHODS above
        raise ValueError(f"Unsupported PEFT method {method!r}")

    peft_model = get_peft_model(model, config)

    if method == "lora_fa":
        for name, param in peft_model.named_parameters():
            if "lora_A" in name:
                param.requires_grad = False
        logger.info("LoRA-FA: froze lora_A matrices (only lora_B + head train)")

    peft_model.print_trainable_parameters()
    logger.info(
        "Applied %s adapter: r=%d, alpha=%d, dropout=%.2f, targets=%s",
        method,
        r,
        alpha,
        dropout,
        target_modules,
    )

    return peft_model


def apply_lora(
    model: nn.Module,
    r: int = 8,
    alpha: int = 16,
    dropout: float = 0.1,
    use_dora: bool = False,
    target_modules: list[str] | None = None,
) -> PeftModel:
    """Apply LoRA or DoRA adapter to MobileNetV2 (legacy entry point)."""
    return apply_peft(
        model,
        method="dora" if use_dora else "lora",
        r=r,
        alpha=alpha,
        dropout=dropout,
        target_modules=target_modules,
    )


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
    logger.info("Saved adapter to %s (%.2f MB)", save_path, total_size / (1024 * 1024))


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
