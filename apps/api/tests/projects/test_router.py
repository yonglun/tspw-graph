from io import BytesIO

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.auth.dependencies import require_ready_admin
from app.auth.models import AdminAccount
from app.projects.files import UploadStore
from app.projects.repository import ProjectRepository
from app.projects.router import get_project_service, router
from app.projects.router import get_job_repository, get_upload_service
from app.projects.service import ProjectService, ProjectUploadService
from app.jobs.repository import JobRepository


class FakeGraphWriter:
    def delete_project(self, project_id: str) -> None:
        return None


def make_client(tmp_path) -> tuple[TestClient, ProjectRepository]:
    repository = ProjectRepository(
        create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    )
    uploads = UploadStore(tmp_path)
    repository.ensure_builtin_project("xiaoao", "笑傲江湖")
    ProjectUploadService(repository, uploads).create(
        title="测试小说", filename="book.txt", stream=BytesIO(b"text")
    )
    service = ProjectService(repository, uploads, FakeGraphWriter())
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_ready_admin] = lambda: AdminAccount(
        id="admin-test", username="admin", normalized_username="admin", password_hash="hash"
    )
    app.dependency_overrides[get_project_service] = lambda: service
    app.dependency_overrides[get_upload_service] = lambda: ProjectUploadService(
        repository, uploads
    )
    app.dependency_overrides[get_job_repository] = lambda: JobRepository(
        repository.engine
    )
    return TestClient(app), repository


def test_list_and_get_projects(tmp_path):
    client, repository = make_client(tmp_path)
    response = client.get("/api/projects")
    assert response.status_code == 200
    assert {item["title"] for item in response.json()} == {"笑傲江湖", "测试小说"}
    user_project = next(item for item in repository.list_projects() if not item.is_builtin)
    assert client.get(f"/api/projects/{user_project.id}").json()["title"] == "测试小说"


def test_delete_is_idempotent_and_builtin_is_forbidden(tmp_path):
    client, repository = make_client(tmp_path)
    user_project = next(item for item in repository.list_projects() if not item.is_builtin)
    assert client.delete(f"/api/projects/{user_project.id}").status_code == 204
    assert client.delete(f"/api/projects/{user_project.id}").status_code == 204
    response = client.delete("/api/projects/xiaoao")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "BUILTIN_PROJECT_READ_ONLY"


def test_upload_creates_project_and_queued_job(tmp_path):
    client, _ = make_client(tmp_path)
    response = client.post(
        "/api/projects/upload",
        data={"title": "上传小说", "model_profile_id": "fixed:test"},
        files={"file": ("upload.txt", "第一章\n测试人物出现。".encode(), "text/plain")},
    )
    assert response.status_code == 201
    assert response.json()["project"]["title"] == "上传小说"
    assert response.json()["job"]["status"] == "QUEUED"
    assert response.json()["job"]["kind"] == "FULL_BUILD"


def test_upload_rejects_unknown_profile_and_wrong_type(tmp_path):
    client, _ = make_client(tmp_path)
    unknown = client.post(
        "/api/projects/upload",
        data={"title": "上传小说", "model_profile_id": "unknown"},
        files={"file": ("upload.txt", b"text", "text/plain")},
    )
    assert unknown.status_code == 422
    wrong_type = client.post(
        "/api/projects/upload",
        data={"title": "上传小说", "model_profile_id": "fixed:test"},
        files={"file": ("upload.pdf", b"text", "application/pdf")},
    )
    assert wrong_type.status_code == 415
