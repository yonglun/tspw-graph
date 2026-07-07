from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field
from sqlalchemy import DateTime, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.projects.models import Base


class ReviewItemType(StrEnum):
    FACT = "FACT"
    DUPLICATE_ENTITY = "DUPLICATE_ENTITY"
    ALIAS_SPLIT = "ALIAS_SPLIT"


class ReviewItemStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class ReviewSource(StrEnum):
    RULE = "rule"
    MODEL = "model"
    MANUAL = "manual"


class ReviewActionType(StrEnum):
    ACCEPT_FACT = "accept_fact"
    REJECT_FACT = "reject_fact"
    MERGE_ENTITIES = "merge_entities"
    SPLIT_ALIAS = "split_alias"
    DISMISS_ITEM = "dismiss_item"


class ReviewItem(Base):
    __tablename__ = "review_items"
    __table_args__ = (
        UniqueConstraint("project_id", "fingerprint", name="uq_review_item_fingerprint"),
    )

    id: Mapped[str] = mapped_column(
        String(80), primary_key=True, default=lambda: f"review-{uuid4().hex}"
    )
    project_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ReviewItemStatus.OPEN.value, index=True
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    fingerprint: Mapped[str] = mapped_column(String(300), nullable=False)
    severity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewAction(Base):
    __tablename__ = "review_actions"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "item_id",
            "action_type",
            "idempotency_key",
            name="uq_review_action_idempotency",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(80), primary_key=True, default=lambda: f"action-{uuid4().hex}"
    )
    project_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    item_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(120), nullable=False, default="local_reviewer")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class QualitySnapshot(Base):
    __tablename__ = "quality_snapshots"

    id: Mapped[str] = mapped_column(
        String(80), primary_key=True, default=lambda: f"quality-{uuid4().hex}"
    )
    project_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class ReviewItemCreate(BaseModel):
    item_type: ReviewItemType
    source: ReviewSource
    reason_code: str = Field(min_length=1)
    target: dict[str, Any]
    evidence_ids: list[str] = Field(default_factory=list)
    fingerprint: str = Field(min_length=1)
    severity: int = Field(default=0, ge=0, le=100)


class ReviewItemRead(ReviewItemCreate):
    id: str
    project_id: str
    status: ReviewItemStatus
    created_at: datetime
    resolved_at: datetime | None = None


class ReviewActionRead(BaseModel):
    id: str
    project_id: str
    item_id: str
    action_type: ReviewActionType
    reviewer: str
    payload: dict[str, Any]
    created_at: datetime
