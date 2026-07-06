from collections.abc import Iterator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import create_engine

from app.graph.neo4j import Neo4jGraphWriter
from app.jobs.repository import JobRepository
from app.jobs.router import JobSnapshot
from app.projects.files import InvalidUpload, UploadStore
from app.projects.repository import ProjectRepository
from app.projects.service import (
    BuiltinProjectError,
    ProjectNotFoundError,
    ProjectService,
    ProjectUploadService,
)
from app.settings import get_settings

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    is_builtin: bool
    source_encoding: str | None
    source_size: int | None
    created_at: datetime
    updated_at: datetime


class ProjectCreated(BaseModel):
    project: ProjectSummary
    job: JobSnapshot


def get_project_service() -> Iterator[ProjectService]:
    settings = get_settings()
    projects = ProjectRepository(create_engine(settings.sqlite_url))
    projects.ensure_builtin_project("xiaoao", "笑傲江湖")
    graph = Neo4jGraphWriter.from_settings(settings)
    try:
        yield ProjectService(projects, UploadStore(settings.data_root), graph)
    finally:
        graph.close()


def get_upload_service() -> ProjectUploadService:
    settings = get_settings()
    return ProjectUploadService(
        ProjectRepository(create_engine(settings.sqlite_url)),
        UploadStore(settings.data_root, settings.max_upload_bytes),
    )


def get_job_repository() -> JobRepository:
    return JobRepository(create_engine(get_settings().sqlite_url))


Service = Annotated[ProjectService, Depends(get_project_service)]
UploadService = Annotated[ProjectUploadService, Depends(get_upload_service)]
Jobs = Annotated[JobRepository, Depends(get_job_repository)]


@router.post("/upload", status_code=201, response_model=ProjectCreated)
def upload_project(
    upload_service: UploadService,
    jobs: Jobs,
    title: Annotated[str, Form(min_length=1, max_length=300)],
    model_profile_id: Annotated[str, Form(min_length=1, max_length=100)],
    file: Annotated[UploadFile, File()],
) -> ProjectCreated:
    if model_profile_id not in {profile.id for profile in get_settings().model_profiles}:
        raise HTTPException(422, detail={"code": "UNKNOWN_MODEL_PROFILE"})
    try:
        project = upload_service.create(
            title=title,
            filename=file.filename or "",
            stream=file.file,
        )
    except InvalidUpload as error:
        code = str(error)
        status_code = {
            "FILE_TOO_LARGE": 413,
            "TXT_ONLY": 415,
            "UNSUPPORTED_ENCODING": 415,
            "EMPTY_FILE": 422,
            "INVALID_PROJECT_PATH": 422,
        }.get(code, 422)
        raise HTTPException(status_code, detail={"code": code}) from error
    try:
        job = jobs.create(project.id, model_profile_id)
    except Exception:
        upload_service.uploads.delete_project(project.id)
        upload_service.projects.delete(project.id)
        raise
    return ProjectCreated(
        project=ProjectSummary.model_validate(project),
        job=JobSnapshot.model_validate(job),
    )


@router.get("", response_model=list[ProjectSummary])
def list_projects(service: Service) -> list[ProjectSummary]:
    return [ProjectSummary.model_validate(project) for project in service.list()]


@router.get("/{project_id}", response_model=ProjectSummary)
def get_project(project_id: str, service: Service) -> ProjectSummary:
    try:
        return ProjectSummary.model_validate(service.get(project_id))
    except ProjectNotFoundError as error:
        raise HTTPException(
            status_code=404, detail={"code": "PROJECT_NOT_FOUND"}
        ) from error


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, service: Service) -> Response:
    try:
        service.delete(project_id)
    except BuiltinProjectError as error:
        raise HTTPException(
            status_code=403, detail={"code": "BUILTIN_PROJECT_READ_ONLY"}
        ) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)
