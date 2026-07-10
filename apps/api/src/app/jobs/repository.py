from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, func, inspect, or_, select, text
from sqlalchemy.orm import Session

from app.jobs.models import (
    TERMINAL_STATUSES,
    Job,
    JobEvent,
    JobKind,
    JobQuality,
    JobStatus,
)
from app.projects.models import Base


class JobRepository:
    def __init__(
        self, engine: Engine, clock: Callable[[], datetime] | None = None
    ) -> None:
        self.engine = engine
        self.clock = clock or (lambda: datetime.now(UTC))
        Base.metadata.create_all(engine)
        self._upgrade_job_kind_schema()

    def _upgrade_job_kind_schema(self) -> None:
        if self.engine.dialect.name != "sqlite":
            return
        columns = {item["name"] for item in inspect(self.engine).get_columns("jobs")}
        if "kind" not in columns:
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        "ALTER TABLE jobs ADD COLUMN kind VARCHAR(30) "
                        "NOT NULL DEFAULT 'FULL_BUILD'"
                    )
                )

    def create(
        self,
        project_id: str,
        model_profile_id: str,
        kind: JobKind = JobKind.FULL_BUILD,
    ) -> Job:
        with Session(self.engine) as session:
            job = Job(
                project_id=project_id,
                model_profile_id=model_profile_id,
                kind=kind,
            )
            session.add(job)
            session.commit()
            session.refresh(job)
            job_id = job.id
        self._append_event(job_id)
        return self.get_required(job_id)

    def get(self, job_id: str) -> Job | None:
        with Session(self.engine) as session:
            job = session.get(Job, job_id)
            if job is not None:
                session.expunge(job)
            return job

    def get_required(self, job_id: str) -> Job:
        job = self.get(job_id)
        if job is None:
            raise LookupError(job_id)
        return job

    def claim_next(self, worker_id: str, lease_seconds: int) -> Job | None:
        now = self.clock()
        with Session(self.engine) as session:
            session.execute(text("BEGIN IMMEDIATE"))
            job = session.scalar(
                select(Job)
                .where(
                    Job.status.not_in([status.value for status in TERMINAL_STATUSES]),
                    Job.status != JobStatus.PAUSED,
                    or_(Job.worker_id.is_(None), Job.lease_expires_at < now),
                )
                .order_by(Job.created_at)
                .limit(1)
            )
            if job is None:
                session.commit()
                return None
            if job.status == JobStatus.QUEUED:
                job.status = JobStatus.SPLITTING
            job.worker_id = worker_id
            job.lease_expires_at = now + timedelta(seconds=lease_seconds)
            job.updated_at = now
            session.commit()
            job_id = job.id
        self._append_event(job_id)
        return self.get_required(job_id)

    def set_status(
        self, job_id: str, status: JobStatus, *, error_code: str | None = None
    ) -> Job:
        with Session(self.engine) as session:
            job = session.get(Job, job_id)
            if job is None:
                raise LookupError(job_id)
            job.status = status
            job.error_code = error_code
            job.updated_at = self.clock()
            job.worker_id = None
            job.lease_expires_at = None
            session.commit()
        self._append_event(job_id)
        return self.get_required(job_id)

    def events_after(self, job_id: str, sequence: int) -> list[JobEvent]:
        with Session(self.engine) as session:
            events = list(
                session.scalars(
                    select(JobEvent)
                    .where(JobEvent.job_id == job_id, JobEvent.sequence > sequence)
                    .order_by(JobEvent.sequence)
                )
            )
            for event in events:
                session.expunge(event)
            return events

    def save_quality(self, job_id: str, report: dict) -> None:
        with Session(self.engine) as session:
            quality = session.get(JobQuality, job_id)
            if quality is None:
                quality = JobQuality(job_id=job_id, report=report)
                session.add(quality)
            else:
                quality.report = report
            session.commit()

    def get_quality(self, job_id: str) -> dict | None:
        with Session(self.engine) as session:
            quality = session.get(JobQuality, job_id)
            return None if quality is None else dict(quality.report)

    def _append_event(self, job_id: str) -> None:
        with Session(self.engine) as session:
            job = session.get(Job, job_id)
            if job is None:
                return
            last = session.scalar(
                select(func.max(JobEvent.sequence)).where(JobEvent.job_id == job_id)
            ) or 0
            session.add(
                JobEvent(
                    job_id=job.id,
                    sequence=last + 1,
                    snapshot={
                        "id": job.id,
                        "project_id": job.project_id,
                        "model_profile_id": job.model_profile_id,
                        "kind": str(job.kind),
                        "status": str(job.status),
                        "completed_chunks": job.completed_chunks,
                        "total_chunks": job.total_chunks,
                        "error_code": job.error_code,
                    },
                )
            )
            session.commit()
