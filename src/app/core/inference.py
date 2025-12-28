import torch
from torchvision import transforms
from PIL import Image
from pathlib import Path
from common.paths import BEST_MODEL_PATH
from ml.models.model import build_model
from ml.models.model import build_model, robust_load_state_dict
from ml.utils.device import get_device

# Load once (hackathon-safe)
device = get_device()

# Alphabetical order matches ImageFolder structure
CLASS_NAMES = ["debris", "garbage", "non_civic", "pothole"]

model = None

def get_model():
    global model
    if model is None:
        model = build_model(len(CLASS_NAMES))
        if BEST_MODEL_PATH.exists():
            print(f"🔧 Attempting robust load from {BEST_MODEL_PATH}")
            state_dict = torch.load(BEST_MODEL_PATH, map_location=device)
            robust_load_state_dict(model, state_dict)
        model.to(device)
        model.eval()
    return model

transform = transforms.Compose([
    transforms.Resize((224, 224)),
    transforms.Lambda(lambda img: img.convert("RGB")),
    transforms.ToTensor(),
    # MUST match training normalization
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
])

def predict_issue(image: Image.Image):
    model = get_model()
    img_tensor = transform(image).unsqueeze(0).to(device)

    # Force correct mapping (Alphabetical)
    # 0: debris, 1: garbage, 2: non_civic, 3: pothole
    LABELS = ["debris", "garbage", "non_civic", "pothole"]
    
    # DEBUG: Save what the model 'sees'
    try:
        debug_path = Path("debug_inference_input.jpg")
        image.save(debug_path)
        print(f"DEBUG: Saved inference input to {debug_path.absolute()}")
    except Exception as e:
        print(f"DEBUG Error saving image: {e}")


    with torch.no_grad():
        outputs = model(img_tensor)
        probs = torch.softmax(outputs, dim=1)

    confidence, pred_idx = torch.max(probs, dim=1)
    
    label = LABELS[pred_idx.item()]
    conf_val = round(confidence.item(), 3)

    return {
        "label": label,
        "confidence": conf_val
    }
