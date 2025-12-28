"""
Prepare dataset from balanced gold standard
Replaces the old CIFAR-10 based approach with high-quality balanced data
"""
from pathlib import Path
import shutil
from sklearn.model_selection import train_test_split

# Paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
BALANCED_SOURCE = PROJECT_ROOT / "data" / "balanced_gold"
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"

# Classes
CLASSES = ['pothole', 'garbage', 'debris', 'non_civic']

def prepare_dataset():
    """Prepare train/val/test splits from balanced gold standard"""
    
    print("="*80)
    print("PREPARING DATASET FROM BALANCED GOLD STANDARD")
    print("="*80)
    print()
    
    # Clean raw data directory
    if RAW_DATA_DIR.exists():
        print(f"🗑️  Cleaning {RAW_DATA_DIR}")
        shutil.rmtree(RAW_DATA_DIR)
    
    # Create directories
    for split in ['train', 'val', 'test']:
        for cls in CLASSES:
            (RAW_DATA_DIR / split / cls).mkdir(parents=True, exist_ok=True)
    
    # Process each class
    print("\n📊 SPLITTING CLASSES (70% train / 15% val / 15% test):")
    print("-" * 80)
    
    for cls in CLASSES:
        source_dir = BALANCED_SOURCE / cls
        
        if not source_dir.exists():
            print(f"⚠️  WARNING: {source_dir} not found, skipping...")
            continue
        
        # Collect all images
        images = list(source_dir.glob("*"))
        
        if not images:
            print(f"⚠️  WARNING: No images in {cls}, skipping...")
            continue
        
        print(f"\n{cls.upper()}:")
        print(f"  Total: {len(images)} images")
        
        # Split: 70% train, 15% val, 15% test
        train_imgs, temp_imgs = train_test_split(images, test_size=0.3, random_state=42)
        val_imgs, test_imgs = train_test_split(temp_imgs, test_size=0.5, random_state=42)
        
        print(f"  Train: {len(train_imgs)}")
        print(f"  Val:   {len(val_imgs)}")
        print(f"  Test:  {len(test_imgs)}")
        
        # Copy files
        for img in train_imgs:
            shutil.copy(img, RAW_DATA_DIR / 'train' / cls / img.name)
        
        for img in val_imgs:
            shutil.copy(img, RAW_DATA_DIR / 'val' / cls / img.name)
        
        for img in test_imgs:
            shutil.copy(img, RAW_DATA_DIR / 'test' / cls / img.name)
    
    # Summary
    print("\n" + "="*80)
    print("📊 FINAL DATASET SUMMARY")
    print("="*80)
    
    for split in ['train', 'val', 'test']:
        print(f"\n{split.upper()}:")
        total = 0
        for cls in CLASSES:
            count = len(list((RAW_DATA_DIR / split / cls).glob("*")))
            total += count
            print(f"  {cls:15} : {count}")
        print(f"  {'TOTAL':15} : {total}")
    
    grand_total = sum(len(list((RAW_DATA_DIR / split / cls).glob("*"))) 
                      for split in ['train', 'val', 'test'] 
                      for cls in CLASSES)
    
    print(f"\n✅ Grand Total: {grand_total} images")
    print(f"📁 Output: {RAW_DATA_DIR}")
    print("\n🎯 READY FOR TRAINING")
    print("="*80)

if __name__ == "__main__":
    prepare_dataset()
