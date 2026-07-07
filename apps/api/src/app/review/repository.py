from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.review.models import (
    ReviewAction,
    ReviewActionRead,
    ReviewActionType,
    ReviewItem,
    ReviewItemCreate,
    ReviewItemRead,
    ReviewItemStatus,
    ReviewItemType,
)


class ReviewRepository:
    def __init__(self, session_factory: sessionmaker) -> None:
        self.session_factory = session_factory

    def create_item_once(self, project_id: str, item: ReviewItemCreate) -> ReviewItemRead:
        with self.session_factory() as session:
            row = ReviewItem(project_id=project_id, **item.model_dump(mode="json"))
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(ReviewItem).where(
                        ReviewItem.project_id == project_id,
                        ReviewItem.fingerprint == item.fingerprint,
                    )
                )
                if existing is None:
                    raise
                return self._item(existing)
            session.refresh(row)
            return self._item(row)

    def list_items(
        self,
        project_id: str,
        status: ReviewItemStatus | None,
        item_type: ReviewItemType | None,
        limit: int,
        cursor: str | None,
    ) -> list[ReviewItemRead]:
        statement = select(ReviewItem).where(ReviewItem.project_id == project_id)
        if status is not None:
            statement = statement.where(ReviewItem.status == status.value)
        if item_type is not None:
            statement = statement.where(ReviewItem.item_type == item_type.value)
        if cursor:
            statement = statement.where(ReviewItem.id > cursor)
        rows = _session_rows(
            self.session_factory,
            statement.order_by(ReviewItem.severity.desc(), ReviewItem.id).limit(limit),
        )
        return [self._item(row) for row in rows]

    def count_open(self, project_id: str) -> int:
        with self.session_factory() as session:
            return session.scalar(
                select(func.count()).select_from(ReviewItem).where(
                    ReviewItem.project_id == project_id,
                    ReviewItem.status == ReviewItemStatus.OPEN.value,
                )
            ) or 0

    def get_item(self, project_id: str, item_id: str) -> ReviewItemRead | None:
        with self.session_factory() as session:
            row = session.scalar(
                select(ReviewItem).where(
                    ReviewItem.project_id == project_id,
                    ReviewItem.id == item_id,
                )
            )
            return self._item(row) if row else None

    def resolve_item(self, project_id: str, item_id: str) -> ReviewItemRead:
        return self._finish_item(project_id, item_id, ReviewItemStatus.RESOLVED)

    def dismiss_item(self, project_id: str, item_id: str) -> ReviewItemRead:
        return self._finish_item(project_id, item_id, ReviewItemStatus.DISMISSED)

    def record_action_once(
        self,
        project_id: str,
        item_id: str,
        action_type: ReviewActionType,
        payload: dict[str, Any],
        idempotency_key: str,
        reviewer: str = "local_reviewer",
    ) -> ReviewActionRead:
        with self.session_factory() as session:
            row = ReviewAction(
                project_id=project_id,
                item_id=item_id,
                action_type=action_type.value,
                reviewer=reviewer,
                payload=payload,
                idempotency_key=idempotency_key,
            )
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                existing = session.scalar(
                    select(ReviewAction).where(
                        ReviewAction.project_id == project_id,
                        ReviewAction.item_id == item_id,
                        ReviewAction.action_type == action_type.value,
                        ReviewAction.idempotency_key == idempotency_key,
                    )
                )
                if existing is None:
                    raise
                return self._action(existing)
            session.refresh(row)
            return self._action(row)

    def list_actions(
        self, project_id: str, limit: int, cursor: str | None
    ) -> list[ReviewActionRead]:
        statement = select(ReviewAction).where(ReviewAction.project_id == project_id)
        if cursor:
            statement = statement.where(ReviewAction.id > cursor)
        rows = _session_rows(
            self.session_factory,
            statement.order_by(ReviewAction.created_at.desc(), ReviewAction.id).limit(limit),
        )
        return [self._action(row) for row in rows]

    def _finish_item(
        self, project_id: str, item_id: str, status: ReviewItemStatus
    ) -> ReviewItemRead:
        with self.session_factory() as session:
            row = session.scalar(
                select(ReviewItem).where(
                    ReviewItem.project_id == project_id,
                    ReviewItem.id == item_id,
                )
            )
            if row is None:
                raise ValueError("review_item_not_found")
            row.status = status.value
            row.resolved_at = datetime.now(UTC)
            session.commit()
            session.refresh(row)
            return self._item(row)

    def _item(self, row: ReviewItem) -> ReviewItemRead:
        return ReviewItemRead(
            id=row.id,
            project_id=row.project_id,
            item_type=ReviewItemType(row.item_type),
            status=ReviewItemStatus(row.status),
            source=row.source,
            reason_code=row.reason_code,
            target=row.target,
            evidence_ids=row.evidence_ids,
            fingerprint=row.fingerprint,
            severity=row.severity,
            created_at=row.created_at,
            resolved_at=row.resolved_at,
        )

    def _action(self, row: ReviewAction) -> ReviewActionRead:
        return ReviewActionRead(
            id=row.id,
            project_id=row.project_id,
            item_id=row.item_id,
            action_type=ReviewActionType(row.action_type),
            reviewer=row.reviewer,
            payload=row.payload,
            created_at=row.created_at,
        )


def _session_rows(session_factory: sessionmaker, statement: Select) -> list[Any]:
    with session_factory() as session:
        return list(session.scalars(statement))
