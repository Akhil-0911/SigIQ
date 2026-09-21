import asyncio
from dataclasses import dataclass, field


@dataclass
class JobState:
    job_id: str
    status: str = "queued"  # queued | running | complete | error | cancelled
    stage: str = None
    percent: int = 0
    message: str = ""
    error: str = None
    result: dict = None
    _subscribers: list = field(default_factory=list)
    cancel_requested: bool = False

    def snapshot(self) -> dict:
        return {
            "job_id": self.job_id, "status": self.status, "stage": self.stage,
            "percent": self.percent, "message": self.message, "error": self.error,
        }
