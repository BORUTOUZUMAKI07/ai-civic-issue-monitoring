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


def robust_load_state_dict(model: nn.Module, state_dict: dict):
    """Load state_dict even if classifier size doesn't match."""
    model_dict = model.state_dict()
    filtered_dict = {}
    for k, v in state_dict.items():
        if k in model_dict and v.shape == model_dict[k].shape:
            filtered_dict[k] = v
    model_dict.update(filtered_dict)
    model.load_state_dict(model_dict)
