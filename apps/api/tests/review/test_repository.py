from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.projects.models import Base
from app.review.models import ReviewItemStatus, ReviewItemType, ReviewSource
from app.review.repository import ReviewItemCreate, ReviewRepository


def repository() -> ReviewRepository:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return ReviewRepository(sessionmaker(engine))


def test_create_item_once_is_idempotent_by_project_and_fingerprint():
    repo = repository()
    item = ReviewItemCreate(
        item_type=ReviewItemType.FACT,
        source=ReviewSource.RULE,
        reason_code="LOW_CONFIDENCE_FACT",
        target={"fact_id": "fact-1"},
        evidence_ids=["ev-1"],
        fingerprint="fact:fact-1:LOW_CONFIDENCE_FACT",
        severity=40,
    )

    first = repo.create_item_once("project-a", item)
    second = repo.create_item_once("project-a", item)

    assert first.id == second.id
    assert repo.count_open("project-a") == 1


def test_list_items_filters_by_status_and_type():
    repo = repository()
    repo.create_item_once(
        "project-a",
        ReviewItemCreate(
            item_type=ReviewItemType.FACT,
            source=ReviewSource.RULE,
            reason_code="LOW_CONFIDENCE_FACT",
            target={"fact_id": "fact-1"},
            evidence_ids=[],
            fingerprint="fact:fact-1",
            severity=10,
        ),
    )
    repo.create_item_once(
        "project-a",
        ReviewItemCreate(
            item_type=ReviewItemType.DUPLICATE_ENTITY,
            source=ReviewSource.RULE,
            reason_code="POSSIBLE_DUPLICATE_ENTITY",
            target={"source_entity_id": "e-1", "target_entity_id": "e-2"},
            evidence_ids=[],
            fingerprint="entity:e-1:e-2",
            severity=30,
        ),
    )

    rows = repo.list_items(
        "project-a",
        status=ReviewItemStatus.OPEN,
        item_type=ReviewItemType.DUPLICATE_ENTITY,
        limit=10,
        cursor=None,
    )

    assert [row.reason_code for row in rows] == ["POSSIBLE_DUPLICATE_ENTITY"]
