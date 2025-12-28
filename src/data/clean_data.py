import os
import shutil
import cv2
import torch
from pathlib import Path
from PIL import Image
from transformers import CLIPProcessor, CLIPModel
from tqdm import tqdm
from loguru import logger

# Configuration
INPUT_DIR = Path("external_data")
BASE_ACCEPTED_DIR = Path("data/balanced_gold")
REJECTED_DIR = Path("data/rejected")
BLURRY_DIR = REJECTED_DIR / "blurry"

# Classes defined in your project
CLASSES = ['pothole', 'garbage', 'debris', 'non_civic']

# Thresholds
BLUR_THRESHOLD = 80.0  # Slightly lowered for realism in field surveys
BATCH_SIZE = 8         # Process images in batches for speed

def check_blur(image_path):
    """Returns True if the image is sharp enough, False if blurry."""
    try:
        image = cv2.imread(str(image_path))
        if image is None:
            return False, 0
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        fm = cv2.Laplacian(gray, cv2.CV_64F).var()
        return fm > BLUR_THRESHOLD, fm
    except Exception as e:
        logger.error(f"Error checking blur for {image_path}: {e}")
        return False, 0

def clean_data():
    # Setup directories
    BLURRY_DIR.mkdir(parents=True, exist_ok=True)
    for cls in CLASSES:
        (BASE_ACCEPTED_DIR / cls).mkdir(parents=True, exist_ok=True)

    if not INPUT_DIR.exists():
        logger.error(f"Input directory {INPUT_DIR} does not exist!")
        return

    # Load Zero-Shot Model (CLIP)
    logger.info("Loading CLIP model for multi-class sorting...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32").to(device)
    processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
    
    # Mapping CLASSES to descriptive CLIP prompts
    prompt_map = {
        "pothole": "a photo of a pothole or broken road surface",
        "garbage": "a photo of a trash pile or garbage on the street",
        "debris": "a photo of construction debris(bricks, sand, cement bags) or building waste on the road or fallen trees",
        "non_civic": "a photo of a clean road, building, or random scenery"
    }
    labels = [prompt_map[cls] for cls in CLASSES]
    
    images_to_process = list(INPUT_DIR.rglob("*"))
    images_to_process = [f for f in images_to_process if f.suffix.lower() in [".jpg", ".jpeg", ".png"]]

    if not images_to_process:
        logger.warning(f"No images found in {INPUT_DIR}")
        return

    logger.info(f"Processing {len(images_to_process)} images in batches...")

    # First pass: Blur filter
    sharp_images = []
    for img_path in tqdm(images_to_process, desc="Blur Check"):
        is_sharp, v = check_blur(img_path)
        if not is_sharp:
            shutil.move(str(img_path), str(BLURRY_DIR / img_path.name))
        else:
            sharp_images.append(img_path)

    # Second pass: Batch AI Classification
    for i in tqdm(range(0, len(sharp_images), BATCH_SIZE), desc="AI Sorting"):
        batch_paths = sharp_images[i:i + BATCH_SIZE]
        try:
            images = [Image.open(p).convert("RGB") for p in batch_paths]
            inputs = processor(text=labels, images=images, return_tensors="pt", padding=True).to(device)
            
            with torch.no_grad():
                outputs = model(**inputs)
            
            probs = outputs.logits_per_image.softmax(dim=1)
            
            for j, prob in enumerate(probs):
                best_class_idx = prob.argmax().item()
                target_class = CLASSES[best_class_idx]
                shutil.move(str(batch_paths[j]), str(BASE_ACCEPTED_DIR / target_class / batch_paths[j].name))
                
        except Exception as e:
            logger.error(f"Error processing batch starting at {batch_paths[0]}: {e}")

    logger.info("✅ Multi-class cleaning complete!")
    for cls in CLASSES:
        count = len(list((BASE_ACCEPTED_DIR / cls).glob('*')))
        logger.info(f"  - {cls:10}: {count}")
    logger.info(f"  - Blurry    : {len(list(BLURRY_DIR.glob('*')))}")

if __name__ == "__main__":
    clean_data()
