import os
import uuid
from werkzeug.utils import secure_filename
from flask import current_app


def allowed_image(filename: str) -> bool:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]


def save_uploaded_image(file_storage, subfolder="misc") -> str:
    """
    Never trust the original filename. Generate a random secure name,
    validate extension, and save under UPLOAD_FOLDER/<subfolder>/.
    Returns the relative path stored in the DB.
    """
    if not file_storage or file_storage.filename == "":
        return None
    if not allowed_image(file_storage.filename):
        raise ValueError("Unsupported file type. Allowed: PNG, JPG, JPEG, WEBP")

    ext = secure_filename(file_storage.filename).rsplit(".", 1)[-1].lower()
    random_name = f"{uuid.uuid4().hex}.{ext}"

    target_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], subfolder)
    os.makedirs(target_dir, exist_ok=True)

    full_path = os.path.join(target_dir, random_name)
    file_storage.save(full_path)

    return f"{subfolder}/{random_name}"


def generate_registration_code() -> str:
    return f"FF-REG-{uuid.uuid4().int % 100000:05d}"
