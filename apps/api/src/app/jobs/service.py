from app.jobs.models import InvalidJobTransition, Job, JobStatus, transition
from app.jobs.models import TERMINAL_STATUSES
from app.jobs.repository import JobRepository


class JobNotFoundError(LookupError):
    pass


class QualityNotReadyError(RuntimeError):
    pass


class JobService:
    def __init__(self, repository: JobRepository) -> None:
        self.repository = repository

    def get(self, job_id: str) -> Job:
        job = self.repository.get(job_id)
        if job is None:
            raise JobNotFoundError(job_id)
        return job

    def pause(self, job_id: str) -> Job:
        job = self.get(job_id)
        return self.repository.set_status(job_id, transition(job.status, JobStatus.PAUSED))

    def resume(self, job_id: str) -> Job:
        job = self.get(job_id)
        return self.repository.set_status(job_id, transition(job.status, JobStatus.QUEUED))

    def cancel(self, job_id: str) -> Job:
        job = self.get(job_id)
        if (
            JobStatus(job.status) == JobStatus.IMPORTING
            and job.total_chunks > 0
            and job.completed_chunks >= job.total_chunks
        ):
            raise InvalidJobTransition(
                f"{job.status}->{JobStatus.CANCELLED}"
            )
        return self.repository.set_status(job_id, transition(job.status, JobStatus.CANCELLED))

    def retry(self, job_id: str) -> Job:
        job = self.get(job_id)
        return self.repository.set_status(job_id, transition(job.status, JobStatus.QUEUED))

    def quality(self, job_id: str) -> dict:
        job = self.get(job_id)
        if JobStatus(job.status) not in TERMINAL_STATUSES:
            raise QualityNotReadyError(job_id)
        report = self.repository.get_quality(job_id)
        if report is None:
            raise QualityNotReadyError(job_id)
        return report
