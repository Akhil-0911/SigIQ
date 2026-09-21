from pydantic import BaseModel, Field
from typing import Optional


class AnalysisStartRequest(BaseModel):
    file_id: str = Field(..., description="file_id returned by POST /api/upload")
    format: str = Field(..., description="'iq' or 'wav' -- must match the uploaded file's format")
    sample_rate: Optional[float] = Field(None, description="Required for format='iq' (raw IQ has no header). Ignored for 'wav' (read from file header)")
    center_frequency: Optional[float] = Field(0.0, description="Tuner center frequency in Hz, used to report absolute carrier frequency")
    iq_dtype: Optional[str] = Field("float32", description="Sample dtype for format='iq': int8|uint8|int16|float32|float64")

    mode: Optional[str] = Field("automatic", description="'automatic' tries all enabled candidates; 'manual' uses the manual_* fields directly")
    modulations: Optional[list] = Field(None, description="Automatic mode: modulation names to try (see GET /api/configuration/options)")
    deinterleaving_enabled: Optional[bool] = Field(True, description="Automatic mode: whether to search de-interleaving methods during recovery")
    deinterleaving_types: Optional[list] = Field(None, description="Automatic mode: de-interleaving methods to try")
    fec_enabled: Optional[bool] = Field(True, description="Automatic mode: whether to search FEC methods during recovery")
    fec_types: Optional[list] = Field(None, description="Automatic mode: FEC methods to try")

    manual_modulation: Optional[str] = Field(None, description="Manual mode: exact modulation to demodulate with")
    manual_symbol_rate: Optional[float] = Field(None, description="Manual mode: known symbol rate in Hz")
    manual_deinterleave: Optional[str] = Field(None, description="Manual mode: exact de-interleaving method to apply")
    manual_fec: Optional[str] = Field(None, description="Manual mode: exact FEC method to decode with")


class AnalysisStartResponse(BaseModel):
    job_id: str = Field(..., description="Use with GET /api/analysis/{job_id}, /ws/analysis/{job_id} or GET /api/results/{job_id}")
    status: str = Field(..., description="Always 'queued' immediately after start")


class JobStatusResponse(BaseModel):
    job_id: str
    status: str = Field(..., description="queued | running | complete | error | cancelled")
    stage: Optional[str] = Field(None, description="Current pipeline stage, e.g. FEATURE_EXTRACTION (see core/pipeline/stages.py)")
    percent: int = Field(0, description="Approximate overall progress, 0-100")
    message: Optional[str] = Field(None, description="Human-readable detail for the current stage")
    error: Optional[str] = Field(None, description="Set only when status='error'")
