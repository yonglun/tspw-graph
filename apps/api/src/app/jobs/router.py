import json
import time
from collections.abc import Iterator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import create_engine

from app.jobs.models import (
    TERMINAL_STATUSES,
    InvalidJobTransition,
    Job,
    JobKind,
    JobStatus,
)
from app.jobs.repository import JobRepository
from app.jobs.service import JobNotFoundError, JobService, QualityNotReadyError
from app.settings import get_settings

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    project_id: str
    model_profile_id: str
    kind: JobKind
    status: JobStatus
    completed_chunks: int
    total_chunks: int
    error_code: str | None
    created_at: datetime
    updated_at: datetime


def get_job_service() -> JobService:
    settings = get_settings()
    return JobService(JobRepository(create_engine(settings.sqlite_url)))


Service = Annotated[JobService, Depends(get_job_service)]


def execute(operation) -> JobSnapshot:
    try:
        return JobSnapshot.model_validate(operation())
    except JobNotFoundError as error:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND"}) from error
    except InvalidJobTransition as error:
        raise HTTPException(409, detail={"code": "INVALID_JOB_TRANSITION"}) from error


@router.get("/{job_id}", response_model=JobSnapshot)
def get_job(job_id: str, service: Service) -> JobSnapshot:
    return execute(lambda: service.get(job_id))


@router.post("/{job_id}/pause", response_model=JobSnapshot)
def pause(job_id: str, service: Service) -> JobSnapshot:
    return execute(lambda: service.pause(job_id))


@router.post("/{job_id}/resume", response_model=JobSnapshot)
def resume(job_id: str, service: Service) -> JobSnapshot:
    return execute(lambda: service.resume(job_id))


@router.post("/{job_id}/cancel", response_model=JobSnapshot)
def cancel(job_id: str, service: Service) -> JobSnapshot:
    return execute(lambda: service.cancel(job_id))


@router.post("/{job_id}/retry", response_model=JobSnapshot)
def retry(job_id: str, service: Service) -> JobSnapshot:
    return execute(lambda: service.retry(job_id))


@router.get("/{job_id}/quality")
def quality(job_id: str, service: Service) -> dict:
    try:
        return service.quality(job_id)
    except JobNotFoundError as error:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND"}) from error
    except QualityNotReadyError as error:
        raise HTTPException(409, detail={"code": "QUALITY_NOT_READY"}) from error


@router.get("/{job_id}/events")
def events(
    job_id: str,
    service: Service,
    last_event_id: Annotated[int, Header(alias="Last-Event-ID")] = 0,
) -> StreamingResponse:
    service.get(job_id)

    def stream() -> Iterator[str]:
        cursor = last_event_id
        while True:
            found = service.repository.events_after(job_id, cursor)
            for event in found:
                cursor = event.sequence
                yield f"id: {event.sequence}\nevent: job\ndata: {json.dumps(event.snapshot, separators=(',', ':'))}\n\n"
                if JobStatus(event.snapshot["status"]) in TERMINAL_STATUSES:
                    return
            time.sleep(0.25)

    return StreamingResponse(stream(), media_type="text/event-stream")
