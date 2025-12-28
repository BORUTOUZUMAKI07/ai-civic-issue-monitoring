"""
CLIP-based Best Image Selector for MobileNet Training
- Selects top 1500 sharpest images per category
- Uses CLIP for accurate classification
- Strict blur filtering (MobileNet-optimized)
- Ensures pure class separation
"""
import shutil
import cv2
import torch
from pathlib import Path
from PIL import Image
from transformers import CLIPProcessor, CLIPModel
from tqdm import tqdm

# Configuration
INPUT_DIR = Path("external_data/source_images")
BASE_ACCEPTED_DIR = Path("data/balanced_gold")
REJECTED_DIR = Path("data/rejected")
BLURRY_DIR = REJECTED_DIR / "blurry"
LOW_CONFIDENCE_DIR = REJECTED_DIR / "low_confidence"

# Classes
CLASSES = ['pothole', 'garbage', 'debris', 'non_civic']

# Thresholds (MobileNet-optimized)
BLUR_THRESHOLD = 100.0  # Strict threshold for MobileNet
CONFIDENCE_THRESHOLD = 0.65  # High confidence required
TARGET_IMAGES_PER_CLASS = 1500  # Top 1500 per category
BATCH_SIZE = 8

def check_blur(image_path):
    """Returns sharpness score (higher = sharper)"""
    try:
        image = cv2.imread(str(image_path))
        if image is None:
            return 0.0
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        variance = cv2.Laplacian(gray, cv2.CV_64F).var()
        return variance
    except Exception as e:
        print(f"Error checking {image_path}: {e}")
        return 0.0

def select_best_images():
    """Select top 1500 sharpest images per category using CLIP"""
    
    # Setup directories
    BLURRY_DIR.mkdir(parents=True, exist_ok=True)
    LOW_CONFIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    for cls in CLASSES:
        (BASE_ACCEPTED_DIR / cls).mkdir(parents=True, exist_ok=True)

    if not INPUT_DIR.exists():
        print(f"❌ Input directory {INPUT_DIR} does not exist!")
        return

    # Load CLIP model
    print("🤖 Loading CLIP model for classification...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(device)
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    
    # Enhanced prompts for better accuracy
    prompt_map = {
        "pothole": "a clear photo of a pothole or damaged road surface with cracks",
        "garbage": "a clear photo of trash, waste, or garbage pile on the street",
        "debris": "a clear photo of construction debris, rubble, bricks, or fallen trees on the road",
        "non_civic": "a clear photo of a clean road, building, vehicle, or normal scenery"
    }
    labels = [prompt_map[cls] for cls in CLASSES]
    
    # Collect all images
    images_to_process = list(INPUT_DIR.rglob("*"))
    images_to_process = [f for f in images_to_process if f.suffix.lower() in [".jpg", ".jpeg", ".png"]]
    
    if not images_to_process:
        print(f"⚠️  No images found in {INPUT_DIR}")
        return

    print(f"\n📊 Processing {len(images_to_process)} images...")
    print(f"🎯 Target: Top {TARGET_IMAGES_PER_CLASS} sharpest images per category")
    print(f"🔍 Blur threshold: {BLUR_THRESHOLD} (MobileNet-optimized)")
    print(f"✅ Confidence threshold: {CONFIDENCE_THRESHOLD}")
    
    # Step 1: Blur filter + sharpness scoring
    print("\n🔍 Step 1: Blur detection and sharpness scoring...")
    sharp_images = []
    
    for img_path in tqdm(images_to_process, desc="Blur Check"):
        sharpness = check_blur(img_path)
        if sharpness > BLUR_THRESHOLD:
            sharp_images.append((img_path, sharpness))
        else:
            shutil.move(str(img_path), str(BLURRY_DIR / img_path.name))
    
    print(f"✅ {len(sharp_images)} sharp images | {len(images_to_process) - len(sharp_images)} blurry (rejected)")
    
    # Step 2: CLIP classification with confidence scoring
    print("\n🤖 Step 2: AI classification with confidence scoring...")
    
    # Store: {class: [(path, sharpness, confidence), ...]}
    classified_images = {cls: [] for cls in CLASSES}
    
    for i in tqdm(range(0, len(sharp_images), BATCH_SIZE), desc="AI Sorting"):
        batch = sharp_images[i:i + BATCH_SIZE]
        batch_paths = [item[0] for item in batch]
        batch_sharpness = [item[1] for item in batch]
        
        try:
            images = [Image.open(p).convert("RGB") for p in batch_paths]
            inputs = processor(text=labels, images=images, return_tensors="pt", padding=True).to(device)
            
            with torch.no_grad():
                outputs = model(**inputs)
            
            probs = outputs.logits_per_image.softmax(dim=1)
            
            for j, prob in enumerate(probs):
                best_class_idx = prob.argmax().item()
                confidence = prob[best_class_idx].item()
                target_class = CLASSES[best_class_idx]
                
                if confidence >= CONFIDENCE_THRESHOLD:
                    classified_images[target_class].append(
                        (batch_paths[j], batch_sharpness[j], confidence)
                    )
                else:
                    # Low confidence - reject
                    dest = LOW_CONFIDENCE_DIR / f"{target_class}_{confidence:.2f}_{batch_paths[j].name}"
                    shutil.move(str(batch_paths[j]), str(dest))
                    
        except Exception as e:
            print(f"Error processing batch: {e}")
    
    # Step 3: Select top N sharpest per class
    print("\n🏆 Step 3: Selecting top images per category...")
    print("="*60)
    
    for cls in CLASSES:
        candidates = classified_images[cls]
        
        if not candidates:
            print(f"  {cls:12} : 0 images (⚠️  No high-confidence matches)")
            continue
        
        # Sort by sharpness (descending)
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        # Take top N
        selected = candidates[:TARGET_IMAGES_PER_CLASS]
        
        # Move selected images
        for img_path, sharpness, confidence in selected:
            dest = BASE_ACCEPTED_DIR / cls / img_path.name
            shutil.move(str(img_path), str(dest))
        
        # Move remaining to rejected
        remaining = candidates[TARGET_IMAGES_PER_CLASS:]
        for img_path, sharpness, confidence in remaining:
            dest = REJECTED_DIR / f"excess_{cls}" / img_path.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(img_path), str(dest))
        
        avg_sharpness = sum(x[1] for x in selected) / len(selected)
        avg_confidence = sum(x[2] for x in selected) / len(selected)
        
        print(f"  {cls:12} : {len(selected):4} selected | Avg Sharpness: {avg_sharpness:.1f} | Avg Confidence: {avg_confidence:.2f}")
    
    # Final summary
    print("\n" + "="*60)
    print("✅ SELECTION COMPLETE!")
    print("="*60)
    
    total_selected = sum(len(list((BASE_ACCEPTED_DIR / cls).glob("*"))) for cls in CLASSES)
    total_blurry = len(list(BLURRY_DIR.glob("*")))
    total_low_conf = len(list(LOW_CONFIDENCE_DIR.glob("*")))
    
    print(f"  Selected (Best): {total_selected}")
    print(f"  Rejected (Blur): {total_blurry}")
    print(f"  Rejected (Low Confidence): {total_low_conf}")
    print(f"\n📁 Output: {BASE_ACCEPTED_DIR}")
    print("🎯 READY FOR MOBILENET TRAINING!")
    print("="*60)

if __name__ == "__main__":
    select_best_images()
