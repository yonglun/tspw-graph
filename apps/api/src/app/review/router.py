from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.projects.models import Base
from app.review.graph import ReviewGraphRepository
from app.review.models import (
    ReviewItemCreate,
    ReviewItemStatus,
    ReviewItemType,
    ReviewSource,
)
from app.review.repository import ReviewRepository
from app.review.service import ReviewActionRequest, ReviewService
from app.settings import Settings
from app.auth.dependencies import require_ready_admin
from app.auth.models import AdminAccount

router = APIRouter(
    prefix="/api/projects/{project_id}/review",
    tags=["review"],
    dependencies=[Depends(require_ready_admin)],
)


class ManualReviewItemRequest(BaseModel):
    item_type: ReviewItemType
    reason_code: str = Field(min_length=1)
    target: dict[str, str]
    evidence_ids: list[str] = Field(default_factory=list)
    fingerprint: str = Field(min_length=1)
    severity: int = Field(default=10, ge=0, le=100)


class MergeEntitiesRequest(BaseModel):
    source_entity_id: str = Field(min_length=1)
    target_entity_id: str = Field(min_length=1)
    idempotency_key: str | None = None


def service() -> ReviewService:
    settings = Settings()
    engine = create_engine(settings.sqlite_url)
    Base.metadata.create_all(engine)
    return ReviewService(
        ReviewRepository(sessionmaker(engine)),
        ReviewGraphRepository.from_settings(settings),
    )


@router.get("/summary")
def summary(project_id: str):
    return service().summary(project_id)


@router.get("/items")
def list_items(
    project_id: str,
    status: ReviewItemStatus | None = None,
    item_type: ReviewItemType | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
):
    return {
        "items": service().repository.list_items(
            project_id, status, item_type, limit, cursor
        )
    }


@router.post("/items")
def create_item(project_id: str, item: ManualReviewItemRequest):
    return service().repository.create_item_once(
        project_id,
        ReviewItemCreate(source=ReviewSource.MANUAL, **item.model_dump()),
    )


@router.post("/items/{item_id}/actions")
def apply_action(
    project_id: str,
    item_id: str,
    request: ReviewActionRequest,
    admin: AdminAccount = Depends(require_ready_admin),
):
    try:
        return service().apply_action(
            project_id, item_id, request, reviewer=admin.username
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/entities/merge")
def merge_entities(
    project_id: str,
    request: MergeEntitiesRequest,
    admin: AdminAccount = Depends(require_ready_admin),
):
    try:
        return service().merge_entities(
            project_id,
            source_entity_id=request.source_entity_id,
            target_entity_id=request.target_entity_id,
            idempotency_key=request.idempotency_key,
            reviewer=admin.username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/audit")
def audit(
    project_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
):
    return {"actions": service().audit(project_id, limit=limit, cursor=cursor)}


@router.post("/scan")
def scan(project_id: str):
    return service().scan(project_id)
