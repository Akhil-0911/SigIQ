import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from backend.app.api import upload, analysis, configuration, results, websocket
from backend.app.jobs.job_manager import job_manager

app = FastAPI(
    title="Signal Analysis System",
    version="0.1.0",
    description=(
        "Backend API for automated .iq/.wav signal analysis: parameter extraction, "
        "modulation identification, demodulation, de-interleaving, FEC decoding and "
        "bit-stream correlation. This API only orchestrates jobs — all DSP runs in "
        "the independent `core/` engine (see /api/health for a liveness check).\n\n"
        "Typical flow: `POST /api/upload` -> `POST /api/analysis/start` -> "
        "watch `/ws/analysis/{job_id}` or poll `GET /api/analysis/{job_id}` -> "
        "`GET /api/results/{job_id}`."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(analysis.router)
app.include_router(configuration.router)
app.include_router(results.router)
app.include_router(websocket.router)


@app.on_event("startup")
async def bind_event_loop():
    job_manager.bind_loop(asyncio.get_running_loop())


@app.get("/api/health", tags=["health"], summary="Liveness check")
async def health():
    """Returns 200 if the API process is up. Does not check the core DSP engine."""
    return {"status": "ok"}


FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
