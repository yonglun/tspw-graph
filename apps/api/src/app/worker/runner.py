from collections.abc import Callable, Mapping
import logging

from app.extraction.providers import ProviderError
from app.jobs.models import TERMINAL_STATUSES, Job, JobStatus
from app.jobs.repository import JobRepository


logger = logging.getLogger(__name__)

NEXT_STATUS = {
    JobStatus.SPLITTING: JobStatus.EXTRACTING,
    JobStatus.EXTRACTING: JobStatus.RESOLVING,
    JobStatus.RESOLVING: JobStatus.VALIDATING,
    JobStatus.VALIDATING: JobStatus.IMPORTING,
    JobStatus.IMPORTING: JobStatus.COMPLETED,
}


class WorkerRunner:
    def __init__(
        self,
        repository: JobRepository,
        *,
        worker_id: str,
        handlers: Mapping[JobStatus, Callable[[Job], None]],
        lease_seconds: int = 60,
    ) -> None:
        self.repository = repository
        self.worker_id = worker_id
        self.handlers = handlers
        self.lease_seconds = lease_seconds

    def run_once(self) -> bool:
        job = self.repository.claim_next(self.worker_id, self.lease_seconds)
        if job is None:
            return False
        handler = self.handlers.get(job.status)
        if handler is None:
            self.repository.set_status(job.id, JobStatus.FAILED, error_code="STAGE_HANDLER_MISSING")
            return True
        try:
            handler(job)
            current = self.repository.get_required(job.id)
            if JobStatus(current.status) in TERMINAL_STATUSES:
                return True
            self.repository.set_status(job.id, NEXT_STATUS[job.status])
        except ProviderError as error:
            current = self.repository.get_required(job.id)
            if JobStatus(current.status) in TERMINAL_STATUSES:
                return True
            logger.exception(
                "Worker stage failed job_id=%s project_id=%s stage=%s error_code=%s",
                job.id,
                job.project_id,
                str(job.status),
                error.code,
                extra={
                    "job_id": job.id,
                    "project_id": job.project_id,
                    "stage": str(job.status),
                    "error_code": error.code,
                },
            )
            self.repository.set_status(job.id, JobStatus.FAILED, error_code=error.code)
        except Exception:
            current = self.repository.get_required(job.id)
            if JobStatus(current.status) in TERMINAL_STATUSES:
                return True
            logger.exception(
                "Worker stage failed job_id=%s project_id=%s stage=%s error_code=%s",
                job.id,
                job.project_id,
                str(job.status),
                "WORKER_STAGE_FAILED",
                extra={
                    "job_id": job.id,
                    "project_id": job.project_id,
                    "stage": str(job.status),
                    "error_code": "WORKER_STAGE_FAILED",
                },
            )
            self.repository.set_status(job.id, JobStatus.FAILED, error_code="WORKER_STAGE_FAILED")
        return True
