from fastapi import APIRouter, HTTPException

from backend.app.jobs.job_manager import job_manager

router = APIRouter(prefix="/api/results", tags=["results"])


@router.get(
    "/{job_id}",
    summary="Fetch the full AnalysisResult for a completed job",
    description=(
        "Returns 409 if the job hasn't finished yet, 422 if it errored, 404 if "
        "job_id is unknown. On success, returns the serialized AnalysisResult: "
        "features, estimate, hypotheses (all scored modulation candidates, "
        "best-first), best_hypothesis, recovered (de-interleave+FEC result), "
        "bitstream (header/payload correlation), and visualizations "
        "(waveform/spectrum/waterfall/constellation data for plotting)."
    ),
)
async def get_result(job_id: str):
    try:
        state = job_manager.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown job_id")

    if state.status == "error":
        raise HTTPException(status_code=422, detail=state.error)
    if state.status != "complete":
        raise HTTPException(status_code=409, detail=f"Job not complete (status={state.status})")

    return state.result
