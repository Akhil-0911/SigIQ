from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.jobs.job_manager import job_manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/analysis/{job_id}")
async def analysis_progress_ws(websocket: WebSocket, job_id: str):
    """Streams job progress snapshots as JSON until status is complete/error/cancelled.

    WebSocket routes aren't part of the OpenAPI spec, so this won't appear in
    /docs -- see backend/app/jobs/job_manager.py for the pub/sub mechanism.
    """
    await websocket.accept()
    try:
        state = job_manager.get(job_id)
    except KeyError:
        await websocket.close(code=4404)
        return

    await websocket.send_json(state.snapshot())
    queue = job_manager.subscribe(job_id)
    try:
        while True:
            snapshot = await queue.get()
            await websocket.send_json(snapshot)
            if snapshot["status"] in ("complete", "error", "cancelled"):
                break
    except WebSocketDisconnect:
        pass
