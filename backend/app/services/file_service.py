import os
import uuid
from pathlib import Path

from core.io.metadata_parser import parse_metadata

UPLOAD_DIR = Path(__file__).resolve().parents[3] / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTENSIONS = {".wav", ".iq"}


class FileService:
    @staticmethod
    def save_upload(filename: str, content: bytes) -> dict:
        ext = os.path.splitext(filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported file type '{ext}'. Only .wav and .iq are accepted.")

        file_id = uuid.uuid4().hex
        stored_path = UPLOAD_DIR / f"{file_id}{ext}"
        stored_path.write_bytes(content)

        fmt = "wav" if ext == ".wav" else "iq"
        metadata = parse_metadata(str(stored_path)) if fmt == "wav" else {"format": "iq", "size_bytes": len(content)}

        return {
            "file_id": file_id,
            "filename": filename,
            "path": str(stored_path),
            "format": fmt,
            "metadata": metadata,
        }

    @staticmethod
    def resolve_path(file_id: str, fmt: str) -> str:
        ext = ".wav" if fmt == "wav" else ".iq"
        path = UPLOAD_DIR / f"{file_id}{ext}"
        if not path.exists():
            raise FileNotFoundError(f"No stored file for file_id={file_id}")
        return str(path)
