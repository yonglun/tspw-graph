from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.projects.models import Base
from app.review.models import ReviewActionType, ReviewItemType, ReviewSource
from app.review.repository import ReviewItemCreate, ReviewRepository
from app.review.service import ReviewActionRequest, ReviewService


class FakeReviewGraph:
    def __init__(self):
        self.merges = []
        self.splits = []

    def merge_entities(
        self, project_id: str, source_entity_id: str, target_entity_id: str
    ) -> None:
        self.merges.append((project_id, source_entity_id, target_entity_id))

    def split_alias(
        self,
        project_id: str,
        source_entity_id: str,
        alias: str,
        target_entity_id: str | None,
    ) -> str:
        self.splits.append((project_id, source_entity_id, alias, target_entity_id))
        return target_entity_id or f"{source_entity_id}__alias__{alias}"


def service():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repo = ReviewRepository(sessionmaker(engine))
    graph = FakeReviewGraph()
    return ReviewService(repo, graph), repo, graph


def test_merge_entities_records_graph_action_and_audit():
    svc, repo, graph = service()
    item = repo.create_item_once(
        "project-a",
        ReviewItemCreate(
            item_type=ReviewItemType.DUPLICATE_ENTITY,
            source=ReviewSource.RULE,
            reason_code="POSSIBLE_DUPLICATE_ENTITY",
            target={"source_entity_id": "e-1", "target_entity_id": "e-2"},
            fingerprint="duplicate:e-1:e-2",
            severity=60,
        ),
    )

    result = svc.apply_action(
        "project-a",
        item.id,
        ReviewActionRequest(
            action_type=ReviewActionType.MERGE_ENTITIES,
            payload={"source_entity_id": "e-1", "target_entity_id": "e-2"},
            idempotency_key="merge-e-1-e-2",
        ),
    )

    assert graph.merges == [("project-a", "e-1", "e-2")]
    assert result.action.payload["target_entity_id"] == "e-2"


def test_split_alias_returns_created_entity_id_in_audit_payload():
    svc, repo, graph = service()
    item = repo.create_item_once(
        "project-a",
        ReviewItemCreate(
            item_type=ReviewItemType.ALIAS_SPLIT,
            source=ReviewSource.RULE,
            reason_code="ALIAS_SPLIT_CANDIDATE",
            target={"source_entity_id": "e-1", "alias": "风清扬"},
            fingerprint="alias:e-1:风清扬",
            severity=50,
        ),
    )

    result = svc.apply_action(
        "project-a",
        item.id,
        ReviewActionRequest(
            action_type=ReviewActionType.SPLIT_ALIAS,
            payload={"source_entity_id": "e-1", "alias": "风清扬"},
            idempotency_key="split-e-1-feng",
        ),
    )

    assert graph.splits == [("project-a", "e-1", "风清扬", None)]
    assert result.action.payload["created_entity_id"] == "e-1__alias__风清扬"
