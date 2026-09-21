"""Exposes the static option lists the frontend needs to build its
Configuration panel (modulation/FEC/interleaving choices), sourced from the
same registries the core pipeline itself uses -- no duplicated hardcoded lists."""
from fastapi import APIRouter

from core.hypotheses.modulation import CANDIDATE_REGISTRY
from core.hypotheses.fec import FEC_CANDIDATES
from core.hypotheses.interleaving import INTERLEAVING_CANDIDATES

router = APIRouter(prefix="/api/configuration", tags=["configuration"])


@router.get(
    "/options",
    summary="List available modulation / FEC / de-interleaving / IQ-dtype options",
    description="Pulled live from the core registries (core/hypotheses/*), so this "
                "always matches what the pipeline actually supports.",
)
async def get_options():
    return {
        "modulations": [c.name for c in CANDIDATE_REGISTRY],
        "fec_types": [f for f in FEC_CANDIDATES if f != "none"],
        "deinterleaving_types": [t for t in INTERLEAVING_CANDIDATES if t != "none"],
        "iq_dtypes": ["int8", "uint8", "int16", "float32", "float64"],
    }
