import torch.nn as nn
from torchvision import models


def build_model(num_classes: int, unfreeze_last_n: int = 0):
    """Build MobileNetV2 for transfer learning."""
    model = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.DEFAULT)

    if unfreeze_last_n > 0:
        for param in model.parameters():
            param.requires_grad = False
        num_blocks = len(model.features)
        start_index = max(0, num_blocks - unfreeze_last_n)
        for i in range(start_index, num_blocks):
            for param in model.features[i].parameters():
                param.requires_grad = True
    else:
        for param in model.parameters():
            param.requires_grad = False

    model.classifier[1] = nn.Linear(model.last_channel, num_classes)
    return model


def build_peft_model(
    num_classes: int,
    method: str = "lora",
    lora_r: int = 8,
    lora_alpha: int = 16,
    lora_dropout: float = 0.1,
    unfreeze_last_n: int = 0,
    total_step: int = 300,
):
    """Build MobileNetV2 with a PEFT adapter.

    Returns a PeftModel ready for parameter-efficient fine-tuning.
    Only ~0.1-4% of parameters are trainable.
    """
    from src.ml.training.peft_wrapper import apply_peft

    base_model = build_model(num_classes, unfreeze_last_n=unfreeze_last_n)
    return apply_peft(
        base_model,
        method=method,
        r=lora_r,
        alpha=lora_alpha,
        dropout=lora_dropout,
        total_step=total_step,
    )


def robust_load_state_dict(model: nn.Module, state_dict: dict):
    """Load state_dict even if classifier size doesn't match."""
    model_dict = model.state_dict()
    filtered_dict = {}
    for k, v in state_dict.items():
        if k in model_dict and v.shape == model_dict[k].shape:
            filtered_dict[k] = v
    model_dict.update(filtered_dict)
    model.load_state_dict(model_dict)
