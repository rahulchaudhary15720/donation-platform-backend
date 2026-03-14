import cloudinary, cloudinary.uploader
from fastapi import HTTPException
from app.core.config import settings

cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET
)

def upload(file, folder="proofs"):
    try:
        result = cloudinary.uploader.upload(file.file, folder=folder)
        return result["secure_url"]
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"File upload service unavailable: {str(e)}"
        )
