from fastapi import APIRouter, UploadFile, File, HTTPException

from backend.app.schemas.signal import FileMetadataResponse
from backend.app.services.file_service import FileService

router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.post(
    "",
    response_model=FileMetadataResponse,
    summary="Upload a .iq or .wav signal file",
    description=(
        "Stores the file under data/uploads/{file_id}.{ext} and extracts cheap "
        "header metadata (no DSP is run here). For .wav, sample_rate/channels/"
        "duration come from the file header. For .iq, only file size is known — "
        "raw IQ has no header, so sample_rate/dtype must be supplied later in "
        "POST /api/analysis/start."
    ),
)
async def upload_file(file: UploadFile = File(..., description="A .iq or .wav file")):
    content = await file.read()
    try:
        saved = FileService.save_upload(file.filename, content)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "file_id": saved["file_id"],
        "filename": saved["filename"],
        "format": saved["format"],
        "metadata": saved["metadata"],
    }
