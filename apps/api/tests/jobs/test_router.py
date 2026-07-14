from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import require_ready_admin
from app.auth.models import AdminAccount
from app.jobs.models import JobStatus
from app.jobs.repository import JobRepository
from app.jobs.router import get_job_service, router
from app.jobs.service import JobService


def make_client() -> tuple[TestClient, JobRepository]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    repository = JobRepository(engine)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_ready_admin] = lambda: AdminAccount(
        id="admin-test", username="admin", normalized_username="admin", password_hash="hash"
    )
    app.dependency_overrides[get_job_service] = lambda: JobService(repository)
    return TestClient(app), repository


def test_pause_resume_and_retry():
    client, repository = make_client()
    job = repository.create("p-1", "fixed:test")
    assert client.post(f"/api/jobs/{job.id}/pause").json()["status"] == "PAUSED"
    assert client.post(f"/api/jobs/{job.id}/resume").json()["status"] == "QUEUED"
    repository.set_status(job.id, JobStatus.FAILED, error_code="MODEL_TIMEOUT")
    assert client.post(f"/api/jobs/{job.id}/retry").json()["status"] == "QUEUED"


def test_events_resume_after_last_event_id():
    client, repository = make_client()
    job = repository.create("p-1", "fixed:test")
    repository.set_status(job.id, JobStatus.COMPLETED)

    response = client.get(
        f"/api/jobs/{job.id}/events", headers={"Last-Event-ID": "1"}
    )

    assert response.status_code == 200
    assert "id: 2" in response.text
    assert "event: job" in response.text
    assert '"status":"COMPLETED"' in response.text
