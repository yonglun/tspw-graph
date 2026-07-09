from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.review.models import (
    ReviewActionRead,
    ReviewActionType,
    ReviewItemCreate,
    ReviewItemRead,
    ReviewItemType,
    ReviewSource,
)
from app.review.repository import ReviewRepository
from app.review.rules import RuleScanner


class ReviewSummary(BaseModel):
    open_review_items: int
    accepted_facts: int = 0
    rejected_facts: int = 0
    pending_facts: int = 0
    merged_entities: int = 0
    split_aliases: int = 0
    evidence_coverage: float = 0
    review_completion_rate: float = 0
    graph_fact_delta_before_after_review: int = 0


class ReviewScanResult(BaseModel):
    created_items: int


class ReviewActionRequest(BaseModel):
    action_type: ReviewActionType
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None


class ReviewActionResult(BaseModel):
    item: ReviewItemRead
    action: ReviewActionRead


class ReviewService:
    def __init__(self, repository: ReviewRepository, graph) -> None:
        self.repository = repository
        self.graph = graph

    def scan(self, project_id: str) -> ReviewScanResult:
        snapshot = self.graph.review_candidates(project_id)
        items = RuleScanner().scan_candidates(project_id, snapshot.facts, snapshot.entities)
        created = 0
        for item in items:
            before = self.repository.count_open(project_id)
            self.repository.create_item_once(project_id, item)
            after = self.repository.count_open(project_id)
            if after > before:
                created += 1
        return ReviewScanResult(created_items=created)

    def summary(self, project_id: str) -> ReviewSummary:
        return ReviewSummary(open_review_items=self.repository.count_open(project_id))

    def audit(self, project_id: str, limit: int, cursor: str | None):
        return self.repository.list_actions(project_id, limit=limit, cursor=cursor)

    def merge_entities(
        self,
        project_id: str,
        *,
        source_entity_id: str,
        target_entity_id: str,
        idempotency_key: str | None = None,
    ) -> ReviewActionResult:
        if source_entity_id == target_entity_id:
            raise ValueError("merge_same_entity")
        fingerprint = f"manual-merge:{source_entity_id}:{target_entity_id}"
        item = self.repository.create_item_once(
            project_id,
            ReviewItemCreate(
                item_type=ReviewItemType.DUPLICATE_ENTITY,
                source=ReviewSource.MANUAL,
                reason_code="MANUAL_ENTITY_MERGE",
                target={
                    "source_entity_id": source_entity_id,
                    "target_entity_id": target_entity_id,
                },
                fingerprint=fingerprint,
                severity=80,
            ),
        )
        return self.apply_action(
            project_id,
            item.id,
            ReviewActionRequest(
                action_type=ReviewActionType.MERGE_ENTITIES,
                payload={
                    "source_entity_id": source_entity_id,
                    "target_entity_id": target_entity_id,
                },
                idempotency_key=idempotency_key or fingerprint,
            ),
        )

    def apply_action(
        self, project_id: str, item_id: str, request: ReviewActionRequest
    ) -> ReviewActionResult:
        item = self.repository.get_item(project_id, item_id)
        if item is None:
            raise ValueError("review_item_not_found")
        key = request.idempotency_key or f"{request.action_type.value}:{item_id}:{uuid4().hex}"

        if request.action_type == ReviewActionType.ACCEPT_FACT:
            fact_id = self._payload_value(request.payload, "fact_id")
            self.graph.accept_fact(project_id, fact_id)
        elif request.action_type == ReviewActionType.REJECT_FACT:
            fact_id = self._payload_value(request.payload, "fact_id")
            self.graph.reject_fact(project_id, fact_id)
        elif request.action_type == ReviewActionType.MERGE_ENTITIES:
            source_entity_id = self._payload_value(request.payload, "source_entity_id")
            target_entity_id = self._payload_value(request.payload, "target_entity_id")
            if source_entity_id == target_entity_id:
                raise ValueError("merge_same_entity")
            self.graph.merge_entities(project_id, source_entity_id, target_entity_id)
        elif request.action_type == ReviewActionType.SPLIT_ALIAS:
            source_entity_id = self._payload_value(request.payload, "source_entity_id")
            alias = self._payload_value(request.payload, "alias")
            target_entity_id = request.payload.get("target_entity_id")
            if target_entity_id is not None and not isinstance(target_entity_id, str):
                raise ValueError("invalid_payload:target_entity_id")
            created_entity_id = self.graph.split_alias(
                project_id, source_entity_id, alias, target_entity_id
            )
            request.payload["created_entity_id"] = created_entity_id
        elif request.action_type == ReviewActionType.DISMISS_ITEM:
            pass
        else:
            raise ValueError(f"unsupported_action:{request.action_type.value}")

        action = self.repository.record_action_once(
            project_id=project_id,
            item_id=item_id,
            action_type=request.action_type,
            payload=request.payload,
            idempotency_key=key,
        )
        resolved = (
            self.repository.dismiss_item(project_id, item_id)
            if request.action_type == ReviewActionType.DISMISS_ITEM
            else self.repository.resolve_item(project_id, item_id)
        )
        return ReviewActionResult(item=resolved, action=action)

    def _payload_value(self, payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"missing_payload:{key}")
        return value
