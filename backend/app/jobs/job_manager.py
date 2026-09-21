"""In-memory job manager. Analysis runs CPU-bound DSP, so each job executes in
a worker thread (via asyncio.to_thread) while progress is pushed back onto the
event loop thread-safely for any WebSocket subscribers."""
import asyncio
import uuid

from backend.app.jobs.progress_tracker import JobState


class JobManager:
    def __init__(self):
        self._jobs: dict[str, JobState] = {}
        self._queues: dict[str, list[asyncio.Queue]] = {}
        self._loop: asyncio.AbstractEventLoop = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def create_job(self) -> str:
        job_id = uuid.uuid4().hex
        self._jobs[job_id] = JobState(job_id=job_id)
        self._queues[job_id] = []
        return job_id

    def get(self, job_id: str) -> JobState:
        if job_id not in self._jobs:
            raise KeyError(f"Unknown job_id {job_id}")
        return self._jobs[job_id]

    def request_cancel(self, job_id: str):
        self.get(job_id).cancel_requested = True

    def subscribe(self, job_id: str) -> asyncio.Queue:
        q = asyncio.Queue()
        self._queues.setdefault(job_id, []).append(q)
        return q

    def _publish(self, job_id: str):
        state = self._jobs[job_id]
        for q in self._queues.get(job_id, []):
            q.put_nowait(state.snapshot())

    def report_progress(self, job_id: str, stage: str, percent: int, message: str):
        """Thread-safe: called from the worker thread running the DSP pipeline."""
        def _apply():
            state = self._jobs[job_id]
            state.status = "running"
            state.stage = stage
            state.percent = percent
            state.message = message
            self._publish(job_id)

        if self._loop:
            self._loop.call_soon_threadsafe(_apply)
        else:
            _apply()

    def set_result(self, job_id: str, result: dict):
        def _apply():
            state = self._jobs[job_id]
            state.status = "complete"
            state.percent = 100
            state.result = result
            self._publish(job_id)
        if self._loop:
            self._loop.call_soon_threadsafe(_apply)
        else:
            _apply()

    def set_error(self, job_id: str, error: str):
        def _apply():
            state = self._jobs[job_id]
            state.status = "error"
            state.error = error
            self._publish(job_id)
        if self._loop:
            self._loop.call_soon_threadsafe(_apply)
        else:
            _apply()


job_manager = JobManager()
