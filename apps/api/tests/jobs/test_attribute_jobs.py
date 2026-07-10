from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.jobs.repository import JobRepository
from app.jobs.models import Job, JobEvent
from app.projects.files import UploadStore
from app.projects.repository import ProjectRepository
from app.projects.router import (
    get_job_repository,
    get_project_service,
    get_upload_service,
    router,
)
from app.projects.service import ProjectService, ProjectUploadService


class FakeGraphWriter:
    def delete_project(self, project_id: str) -> None:
        return None


def make_client(tmp_path):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    projects = ProjectRepository(engine)
    uploads = UploadStore(tmp_path)
    projects.ensure_builtin_project("xiaoao", "笑傲江湖")
    ProjectUploadService(projects, uploads).create(
        title="测试小说", filename="book.txt", stream=BytesIO(b"text")
    )
    service = ProjectService(projects, uploads, FakeGraphWriter())
    jobs = JobRepository(engine)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_project_service] = lambda: service
    app.dependency_overrides[get_upload_service] = lambda: ProjectUploadService(
        projects, uploads
    )
    app.dependency_overrides[get_job_repository] = lambda: jobs
    return TestClient(app), projects, jobs, uploads


def test_create_attribute_job(tmp_path):
    client, projects, _, _ = make_client(tmp_path)
    user_project = next(
        project for project in projects.list_projects() if not project.is_builtin
    )

    response = client.post(
        f"/api/projects/{user_project.id}/attribute-jobs",
        json={"model_profile_id": "fixed:test"},
    )

    assert response.status_code == 201
    assert response.json()["project_id"] == user_project.id
    assert response.json()["kind"] == "ATTRIBUTE_BACKFILL"
    assert response.json()["status"] == "QUEUED"


def test_attribute_job_rejects_unknown_project(tmp_path):
    client, _, _, _ = make_client(tmp_path)

    response = client.post(
        "/api/projects/missing/attribute-jobs",
        json={"model_profile_id": "fixed:test"},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PROJECT_NOT_FOUND"


def test_attribute_job_rejects_project_without_source(tmp_path):
    client, _, _, _ = make_client(tmp_path)

    response = client.post(
        "/api/projects/xiaoao/attribute-jobs",
        json={"model_profile_id": "fixed:test"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PROJECT_SOURCE_MISSING"


def test_attribute_job_rejects_unknown_profile(tmp_path):
    client, projects, _, _ = make_client(tmp_path)
    user_project = next(
        project for project in projects.list_projects() if not project.is_builtin
    )

    response = client.post(
        f"/api/projects/{user_project.id}/attribute-jobs",
        json={"model_profile_id": "unknown"},
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "UNKNOWN_MODEL_PROFILE"


def test_attribute_job_rejects_missing_stored_source_without_creating_job_or_event(tmp_path):
    client, projects, jobs, uploads = make_client(tmp_path)
    project = next(item for item in projects.list_projects() if not item.is_builtin)
    assert project.source_path is not None
    (uploads.root / project.source_path).unlink()

    response = client.post(
        f"/api/projects/{project.id}/attribute-jobs",
        json={"model_profile_id": "fixed:test"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "PROJECT_SOURCE_MISSING"}}
    with Session(jobs.engine) as session:
        assert session.scalar(select(func.count()).select_from(Job)) == 0
        assert session.scalar(select(func.count()).select_from(JobEvent)) == 0
