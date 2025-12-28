from PIL import Image
from pathlib import Path
from app.core.inference import predict_issue

GOLD_DIR = Path("data/balanced_gold")
CLASSES = ["debris", "garbage", "non_civic", "pothole"]

def run_diagnostic():
    print("--- Starting Inference Diagnostic ---")
    
    for cls in CLASSES:
        class_dir = GOLD_DIR / cls
        if not class_dir.exists():
            print(f"WARN: Class directory {cls} not found!")
            continue
            
        images = list(class_dir.glob("*.jpg")) + list(class_dir.glob("*.jpeg")) + list(class_dir.glob("*.png"))
        if not images:
            print(f"WARN: No images found in {cls}!")
            continue
            
        test_img_path = images[0]
        print(f"Testing Ground Truth: {cls.upper()}")
        print(f"Image: {test_img_path.name}")
        
        try:
            img = Image.open(test_img_path)
            result = predict_issue(img)
            print(f"Prediction: {result['label']} (Confidence: {result['confidence']})")
            
            if result['label'] == cls:
                print("RESULT: MATCH")
            else:
                print("RESULT: MISMATCH")
        except Exception as e:
            print(f"ERROR: {e}")
        print("-" * 30)

if __name__ == "__main__":
    run_diagnostic()
