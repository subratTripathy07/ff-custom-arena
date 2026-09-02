"""Validated, non-executable uploads for payment and match evidence."""
import os
import uuid
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from werkzeug.utils import secure_filename
from flask import current_app


def save_proof(file_storage, category="proofs"):
    if not file_storage or not file_storage.filename:
        return None
    filename = secure_filename(file_storage.filename)
    extension = Path(filename).suffix.lower().lstrip(".")
    if extension not in current_app.config["ALLOWED_PROOF_EXTENSIONS"]:
        raise ValueError("Only image, PDF, and MP4 proof files are allowed.")
    # Images are decoded, which rejects disguised executable files.
    if extension in current_app.config["ALLOWED_IMAGE_EXTENSIONS"]:
        try:
            image = Image.open(file_storage.stream)
            image.verify()
            file_storage.stream.seek(0)
        except (UnidentifiedImageError, OSError):
            raise ValueError("The uploaded image is invalid.")
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > current_app.config["PROOF_MAX_BYTES"]:
        raise ValueError("Proof file is larger than the allowed limit.")
    relative = f"{category}/{uuid.uuid4().hex}.{extension}"
    absolute = os.path.join(current_app.config["UPLOAD_FOLDER"], relative)
    os.makedirs(os.path.dirname(absolute), exist_ok=True)
    file_storage.save(absolute)
    return relative
