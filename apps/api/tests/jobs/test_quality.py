from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import require_ready_admin
from app.auth.models import AdminAccount
from app.extraction.pipeline import QualityReport
from app.jobs.models import JobStatus
from app.jobs.repository import JobRepository
from app.jobs.router import get_job_service, router
from app.jobs.service import JobService


def test_quality_report_requires_terminal_job_and_returns_saved_report():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    repository = JobRepository(engine)
    job = repository.create("p-1", "fixed:test")
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[require_ready_admin] = lambda: AdminAccount(
        id="admin-test",
        username="admin",
        normalized_username="admin",
        password_hash="hash",
    )
    app.dependency_overrides[get_job_service] = lambda: JobService(repository)
    client = TestClient(app)
    assert client.get(f"/api/jobs/{job.id}/quality").status_code == 409
    report = QualityReport(total_chunks=1, successful_chunks=1, accepted_entities=2, accepted_facts=1, accepted_evidence=1, model_calls=1)
    repository.save_quality(job.id, report.model_dump())
    repository.set_status(job.id, JobStatus.COMPLETED)
    assert client.get(f"/api/jobs/{job.id}/quality").json()["accepted_facts"] == 1
