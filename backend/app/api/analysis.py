import asyncio

from fastapi import APIRouter, HTTPException

from backend.app.schemas.analysis import AnalysisStartRequest, AnalysisStartResponse, JobStatusResponse
from backend.app.services.file_service import FileService
from backend.app.jobs.job_manager import job_manager
from backend.app.jobs.analysis_worker import run_analysis_job

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.post(
    "/start",
    response_model=AnalysisStartResponse,
    summary="Start an analysis job for a previously uploaded file",
    description=(
        "Runs the full core pipeline (preprocessing -> isolation -> feature "
        "extraction -> parameter estimation -> candidate scoring -> demodulation "
        "-> de-interleaving/FEC recovery search -> bit-stream correlation) in a "
        "background thread. Returns immediately with a job_id; track progress via "
        "GET /api/analysis/{job_id} or the /ws/analysis/{job_id} WebSocket, then "
        "fetch GET /api/results/{job_id} once status is 'complete'.\n\n"
        "sample_rate is required when format='iq' (raw IQ has no header). "
        "mode='manual' uses manual_modulation/manual_symbol_rate/manual_deinterleave/"
        "manual_fec directly instead of searching all candidates."
    ),
)
async def start_analysis(req: AnalysisStartRequest):
    try:
        file_path = FileService.resolve_path(req.file_id, req.format)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    job_id = job_manager.create_job()
    request_dict = req.model_dump()

    async def _run():
        await asyncio.to_thread(run_analysis_job, job_id, file_path, request_dict)

    asyncio.create_task(_run())
    return AnalysisStartResponse(job_id=job_id, status="queued")


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    summary="Poll a job's status and current pipeline stage",
    description="Use this if you're not using the WebSocket. status is one of "
                "queued|running|complete|error|cancelled.",
)
async def get_analysis_status(job_id: str):
    try:
        state = job_manager.get(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return JobStatusResponse(**state.snapshot())


@router.post(
    "/{job_id}/cancel",
    summary="Request cancellation of a running job",
    description="Best-effort: sets a cancel flag the worker can check between "
                "pipeline stages. Does not forcibly kill an in-progress DSP stage.",
)
async def cancel_analysis(job_id: str):
    try:
        job_manager.request_cancel(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unknown job_id")
    return {"job_id": job_id, "cancel_requested": True}
