"""
Folder-Based Best Image Selector (NO CLIP - Pure Quality Filter)
- Respects your existing folder organization
- Selects top 1500 sharpest images per folder
- NO AI classification (prevents mixing)
- MobileNet-optimized blur filtering
"""
import shutil
import cv2
from pathlib import Path
from tqdm import tqdm

# Configuration
INPUT_DIR = Path("external_data/source_images")
BASE_ACCEPTED_DIR = Path("data/balanced_gold")
REJECTED_DIR = Path("data/rejected")
BLURRY_DIR = REJECTED_DIR / "blurry"

# Folder mapping (source folder → target class)
FOLDER_MAPPING = {
    "potholes": "pothole",
    "pothole": "pothole",
    "garbage": "garbage",
    "debris": "debris",
    "non-civic": "non_civic",
    "non_civic": "non_civic",
    "no": "non_civic",
    "hello": "non_civic",
}

# Thresholds
BLUR_THRESHOLD = 100.0  # Strict for MobileNet
TARGET_IMAGES_PER_CLASS = 1500

def calculate_sharpness(image_path):
    """Calculate sharpness score using Laplacian variance"""
    try:
        image = cv2.imread(str(image_path))
        if image is None:
            return 0.0
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        variance = cv2.Laplacian(gray, cv2.CV_64F).var()
        return variance
    except Exception as e:
        print(f"Error: {image_path} - {e}")
        return 0.0

def select_best_from_folders():
    """Select top N sharpest images from each folder (NO CLIP)"""
    
    print("="*70)
    print("FOLDER-BASED BEST IMAGE SELECTOR (Quality-Only, No AI Mixing)")
    print("="*70)
    
    # Setup directories
    BLURRY_DIR.mkdir(parents=True, exist_ok=True)
    for target_class in set(FOLDER_MAPPING.values()):
        (BASE_ACCEPTED_DIR / target_class).mkdir(parents=True, exist_ok=True)
    
    if not INPUT_DIR.exists():
        print(f"❌ {INPUT_DIR} not found!")
        return
    
    print(f"\n🎯 Target: Top {TARGET_IMAGES_PER_CLASS} sharpest per category")
    print(f"🔍 Blur threshold: {BLUR_THRESHOLD} (MobileNet-optimized)")
    print(f"📁 Source: {INPUT_DIR}")
    print("="*70)
    
    stats = {}
    
    # Process each source folder
    for source_folder, target_class in FOLDER_MAPPING.items():
        folder_path = INPUT_DIR / source_folder
        
        if not folder_path.exists():
            continue
        
        print(f"\n📂 Processing: {source_folder} → {target_class}")
        
        # Collect all images (RECURSIVE - searches subfolders too)
        all_images = [f for f in folder_path.rglob("*") if f.suffix.lower() in [".jpg", ".jpeg", ".png"]]
        
        if not all_images:
            print(f"  ⚠️  No images found")
            continue
        
        print(f"  Found: {len(all_images)} images")
        
        # Calculate sharpness for each image
        print(f"  🔍 Calculating sharpness...")
        image_scores = []
        
        for img_path in tqdm(all_images, desc=f"  Scoring", leave=False):
            sharpness = calculate_sharpness(img_path)
            if sharpness > BLUR_THRESHOLD:
                image_scores.append((img_path, sharpness))
        
        print(f"  ✅ Sharp images: {len(image_scores)}")
        
        if not image_scores:
            print(f"  ⚠️  No sharp images found (all below threshold)")
            continue
        
        # Sort by sharpness (descending)
        image_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Select top N
        selected = image_scores[:TARGET_IMAGES_PER_CLASS]
        rejected_blur = [img for img in all_images if img not in [s[0] for s in image_scores]]
        rejected_excess = image_scores[TARGET_IMAGES_PER_CLASS:]
        
        # Move selected images
        for img_path, sharpness in selected:
            dest = BASE_ACCEPTED_DIR / target_class / img_path.name
            shutil.copy(str(img_path), str(dest))
        
        # Move blurry images
        for img_path in rejected_blur:
            dest = BLURRY_DIR / f"{source_folder}_{img_path.name}"
            shutil.copy(str(img_path), str(dest))
        
        # Move excess (sharp but not top N)
        excess_dir = REJECTED_DIR / f"excess_{target_class}"
        excess_dir.mkdir(parents=True, exist_ok=True)
        for img_path, sharpness in rejected_excess:
            dest = excess_dir / img_path.name
            shutil.copy(str(img_path), str(dest))
        
        avg_sharpness = sum(s[1] for s in selected) / len(selected) if selected else 0
        
        stats[target_class] = {
            "selected": len(selected),
            "blurry": len(rejected_blur),
            "excess": len(rejected_excess),
            "avg_sharpness": avg_sharpness
        }
        
        print(f"  ✅ Selected: {len(selected)} (Avg sharpness: {avg_sharpness:.1f})")
        print(f"  🗑️  Rejected: {len(rejected_blur)} blurry, {len(rejected_excess)} excess")
    
    # Final summary
    print("\n" + "="*70)
    print("📊 FINAL SUMMARY")
    print("="*70)
    
    for cls in sorted(set(FOLDER_MAPPING.values())):
        if cls in stats:
            s = stats[cls]
            print(f"  {cls:12} : {s['selected']:4} selected | Avg Sharpness: {s['avg_sharpness']:.1f}")
    
    total_selected = sum(s["selected"] for s in stats.values())
    total_blurry = sum(s["blurry"] for s in stats.values())
    
    print(f"\n  Total Selected: {total_selected}")
    print(f"  Total Rejected (Blur): {total_blurry}")
    print(f"\n📁 Output: {BASE_ACCEPTED_DIR}")
    print("🎯 READY FOR TRAINING (NO CLASS MIXING!)")
    print("="*70)

if __name__ == "__main__":
    select_best_from_folders()
