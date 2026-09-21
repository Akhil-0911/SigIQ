from pydantic import BaseModel
from typing import Optional, Any


class ResultResponse(BaseModel):
    job_id: str
    features: dict
    estimate: dict
    hypotheses: list
    best_hypothesis: Optional[dict]
    recovered: Optional[dict]
    bitstream: Optional[dict]
    visualizations: dict
