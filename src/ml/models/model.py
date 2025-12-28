import torch.nn as nn
from torchvision import models

def build_model(num_classes: int, unfreeze_last_n: int = 0):
    """
    Builds a MobileNetV2 model for transfer learning.
    
    Args:
        num_classes: Number of output classes.
        unfreeze_last_n: If > 0, unfreeze only the last N blocks of the features.
                         For 8k images, unfreeze_last_n=5 is highly recommended.
    """
    model = models.mobilenet_v2(weights=models.MobileNet_V2_Weights.DEFAULT)

    if unfreeze_last_n > 0:
        # 🪜 PARTIAL FINE-TUNE: Freeze most, unfreeze last N layers of features
        # First, freeze everything
        for param in model.parameters():
            param.requires_grad = False
        
        # Then, unfreeze the last N blocks of features (MobileNetV2 features has 19 blocks)
        num_blocks = len(model.features) # type: ignore
        start_index = max(0, num_blocks - unfreeze_last_n)
        for i in range(start_index, num_blocks):
            for param in model.features[i].parameters(): # type: ignore
                param.requires_grad = True
    else:
        # ❄️ FROZEN BACKBONE: Standard Transfer Learning
        for param in model.parameters():
            param.requires_grad = False

    model.classifier[1] = nn.Linear(
        model.last_channel,
        num_classes
    )

    return model

def robust_load_state_dict(model: nn.Module, state_dict: dict):
    """
    Loads state_dict into model even if the classifier size doesn't match.
    Handy for transitioning from 3-class to 4-class models.
    """
    model_dict = model.state_dict()
    
    # Filter out mismatched weights in the classifier
    filtered_dict = {}
    for k, v in state_dict.items():
        if k in model_dict:
            if v.shape == model_dict[k].shape:
                filtered_dict[k] = v
            else:
                print(f"⚠️  Skipping layer {k} due to shape mismatch: {v.shape} vs {model_dict[k].shape}")
        else:
            print(f"❓ Layer {k} not found in current model, skipping.")

    # Update only the matching layers
    model_dict.update(filtered_dict)
    model.load_state_dict(model_dict)
    
    missing = set(model_dict.keys()) - set(filtered_dict.keys())
    if missing:
        print(f"⚡ Re-initialized {len(missing)} layers (including potentially the classifier head).")
