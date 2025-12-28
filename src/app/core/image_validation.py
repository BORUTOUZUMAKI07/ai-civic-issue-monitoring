from fastapi import UploadFile, HTTPException
from PIL import Image
import io

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp", "heic"}
MAX_FILE_SIZE_MB = 5

def validate_image(file: UploadFile):
    # 1️⃣ Extension check
    ext = file.filename.split(".")[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only JPG and PNG allowed."
        )

    # 2️⃣ File size check
    contents = file.file.read()
    size_mb = len(contents) / (1024 * 1024)
    if size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=400,
            detail="Image too large. Max size is 5MB."
        )

    # 3️⃣ Image integrity check
    try:
        image = Image.open(io.BytesIO(contents))
        image.verify()
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Corrupted or invalid image file."
        )

    # Reset file pointer (VERY IMPORTANT)
    file.file.seek(0)

    return True
