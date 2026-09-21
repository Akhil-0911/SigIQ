"""Runs the core pipeline for one job. Executes in a worker thread so the
FastAPI event loop stays responsive for progress polling / WebSocket pushes."""
import numpy as np

from core.io.iq_reader import read_iq
from core.io.wav_reader import read_wav
from core.pipeline.pipeline_config import PipelineConfig
from core.pipeline.analyzer import run_pipeline

from backend.app.jobs.job_manager import job_manager


def _to_jsonable(obj):
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if hasattr(obj, "__dict__"):
        return {k: _to_jsonable(v) for k, v in vars(obj).items()}
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    return obj


def run_analysis_job(job_id: str, file_path: str, request: dict):
    try:
        fmt = request["format"]
        if fmt == "wav":
            raw = read_wav(file_path, center_frequency=request.get("center_frequency", 0.0))
        else:
            sample_rate = request.get("sample_rate")
            if not sample_rate:
                raise ValueError("sample_rate is required for .iq files (no header available)")
            raw = read_iq(file_path, sample_rate=sample_rate,
                           center_frequency=request.get("center_frequency", 0.0),
                           dtype_name=request.get("iq_dtype", "float32"))

        config = PipelineConfig.from_dict({
            "input": {"format": fmt, "sample_rate": raw.sample_rate, "center_frequency": raw.center_frequency},
            "analysis": {"mode": request.get("mode", "automatic")},
            "modulations": request.get("modulations") or ["BPSK", "QPSK", "16-QAM", "2-FSK", "4-FSK"],
            "deinterleaving": {
                "enabled": request.get("deinterleaving_enabled", True),
                "types": request.get("deinterleaving_types") or ["block", "convolutional", "diagonal", "pseudo_random"],
            },
            "fec": {
                "enabled": request.get("fec_enabled", True),
                "types": request.get("fec_types") or ["convolutional_viterbi", "reed_solomon", "concatenated", "ldpc"],
            },
            "manual": {
                "modulation": request.get("manual_modulation"),
                "symbol_rate": request.get("manual_symbol_rate"),
                "deinterleave": request.get("manual_deinterleave"),
                "fec": request.get("manual_fec"),
            },
        })

        def progress_cb(stage, percent, message):
            job_manager.report_progress(job_id, stage, percent, message)

        result = run_pipeline(raw, config, progress_cb=progress_cb)
        job_manager.set_result(job_id, _to_jsonable(result))
    except Exception as e:
        job_manager.set_error(job_id, str(e))
