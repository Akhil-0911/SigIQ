from pydantic import BaseModel, Field
from typing import Optional


class FileMetadataResponse(BaseModel):
    file_id: str = Field(..., description="Opaque id to reference this file in POST /api/analysis/start")
    filename: str = Field(..., description="Original uploaded filename")
    format: str = Field(..., description="'iq' or 'wav', inferred from the file extension")
    metadata: dict = Field(..., description="Header-derived metadata: sample_rate/channels/duration for .wav, size_bytes for .iq")


class UploadConfig(BaseModel):
    sample_rate: Optional[float] = None
    center_frequency: Optional[float] = 0.0
    iq_dtype: Optional[str] = "float32"
