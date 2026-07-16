from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.projects.models import Base


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    SPLITTING = "SPLITTING"
    EXTRACTING = "EXTRACTING"
    RESOLVING = "RESOLVING"
    VALIDATING = "VALIDATING"
    IMPORTING = "IMPORTING"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"


class JobKind(StrEnum):
    FULL_BUILD = "FULL_BUILD"
    ATTRIBUTE_BACKFILL = "ATTRIBUTE_BACKFILL"


TERMINAL_STATUSES = {JobStatus.CANCELLED, JobStatus.FAILED, JobStatus.COMPLETED}

ALLOWED_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.QUEUED: {JobStatus.SPLITTING, JobStatus.PAUSED, JobStatus.CANCELLED},
    JobStatus.SPLITTING: {
        JobStatus.EXTRACTING, JobStatus.PAUSED, JobStatus.FAILED, JobStatus.CANCELLED
    },
    JobStatus.EXTRACTING: {
        JobStatus.RESOLVING, JobStatus.PAUSED, JobStatus.FAILED, JobStatus.CANCELLED
    },
    JobStatus.RESOLVING: {
        JobStatus.VALIDATING, JobStatus.PAUSED, JobStatus.FAILED, JobStatus.CANCELLED
    },
    JobStatus.VALIDATING: {
        JobStatus.IMPORTING, JobStatus.PAUSED, JobStatus.FAILED, JobStatus.CANCELLED
    },
    JobStatus.IMPORTING: {
        JobStatus.COMPLETED,
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    },
    JobStatus.PAUSED: {JobStatus.QUEUED, JobStatus.CANCELLED},
    JobStatus.FAILED: {JobStatus.QUEUED, JobStatus.CANCELLED},
}


class InvalidJobTransition(ValueError):
    pass


def transition(current: JobStatus, target: JobStatus) -> JobStatus:
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidJobTransition(f"{current}->{target}")
    return target


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(
        String(100), primary_key=True, default=lambda: f"job-{uuid4()}"
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    model_profile_id: Mapped[str] = mapped_column(String(100), nullable=False)
    kind: Mapped[JobKind] = mapped_column(
        String(30), default=JobKind.FULL_BUILD, nullable=False
    )
    status: Mapped[JobStatus] = mapped_column(
        String(30), default=JobStatus.QUEUED, nullable=False
    )
    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    completed_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class JobEvent(Base):
    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class JobQuality(Base):
    __tablename__ = "job_quality"

    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    report: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
