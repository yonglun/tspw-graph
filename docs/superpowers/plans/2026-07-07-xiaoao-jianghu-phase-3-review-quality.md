# 《笑傲江湖》知识图谱阶段三审核质量 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付单机单用户的审核工作台和质量仪表盘，让事实接受/拒绝、实体合并、别名拆出影响默认图谱与问答，并保留可追溯审计日志。

**Architecture:** 在现有 FastAPI + SQLite + Neo4j + React 架构上新增 `review` 后端模块和 `/review` 前端页面。SQLite 保存审核队列、审核动作和质量快照；Neo4j 保存实体/事实当前审核状态、合并指针和默认查询过滤所需字段。图谱页和问答页默认读取审核后有效图谱，原始证据和审计记录不删除。

**Tech Stack:** FastAPI, SQLAlchemy, Neo4j Python Driver, Pydantic, React, TypeScript, React Router, Vitest, Pytest, Playwright, Docker Compose.

## Global Constraints

- 所有审核读写必须带 `project_id`，禁止跨项目修改。
- 第一版不引入账户系统；reviewer 固定为 `local_reviewer`，但数据模型保留 reviewer 字段。
- `ReviewAction` 是 append-only 记录，不更新、不删除。
- `ReviewItem` 状态为 `OPEN / RESOLVED / DISMISSED`。
- `Fact` 状态为 `PENDING / ACCEPTED / REJECTED`。
- `Entity` 状态为 `PENDING / ACCEPTED / MERGED / SPLIT_SOURCE`。
- 审核后图谱是默认视图；图谱和问答必须过滤 `REJECTED` 事实和 `MERGED` source 实体。
- 原始抽取记录和证据不得因审核动作被删除。
- 阶段一教学演示和阶段二在线构建必须继续通过 `make verify`。
- 第一版不做正式登录、权限、多人审批、PostgreSQL、Redis、外部队列、拖拽拆分、自动重抽取。

---

## File Structure

后端新增文件：

- `apps/api/src/app/review/__init__.py`：review package。
- `apps/api/src/app/review/models.py`：Pydantic DTO、枚举和 SQLAlchemy `ReviewItem`、`ReviewAction`、`QualitySnapshot`。
- `apps/api/src/app/review/repository.py`：SQLite 审核队列、动作和快照仓储。
- `apps/api/src/app/review/rules.py`：确定性规则扫描，生成审核项候选。
- `apps/api/src/app/review/graph.py`：Neo4j 审核状态写入和审核后查询辅助。
- `apps/api/src/app/review/service.py`：scan、action、summary、audit 业务编排。
- `apps/api/src/app/review/router.py`：`/api/projects/{project_id}/review/*` API。

后端修改文件：

- `apps/api/src/app/main.py`：注册 review router。
- `apps/api/src/app/projects/models.py`：导入 review SQLAlchemy 模型，确保 `Base.metadata.create_all()` 创建审核表。
- `apps/api/src/app/graph/repository.py`：默认过滤被拒绝事实和已合并 source 实体；详情返回 fact status。
- `apps/api/src/app/graph/models.py`：给 `EntitySummary`、`GraphEdge`、`RelatedFact` 增加可选审核字段。
- `apps/api/src/app/qa/service.py`：保持通过 repository 查询审核后事实，不直接绕过过滤。

后端测试新增/修改：

- `apps/api/tests/review/test_repository.py`
- `apps/api/tests/review/test_rules.py`
- `apps/api/tests/review/test_service_facts.py`
- `apps/api/tests/review/test_service_entities.py`
- `apps/api/tests/review/test_router.py`
- `apps/api/tests/graph/test_review_filters.py`
- `apps/api/tests/qa/test_review_filters.py`

前端新增文件：

- `apps/web/src/features/review/ReviewPage.tsx`
- `apps/web/src/features/review/ReviewSummary.tsx`
- `apps/web/src/features/review/ReviewQueue.tsx`
- `apps/web/src/features/review/ReviewDetail.tsx`
- `apps/web/src/features/review/AuditDrawer.tsx`
- `apps/web/src/features/review/ReviewPage.test.tsx`

前端修改文件：

- `apps/web/src/api/client.ts`：新增 review 类型与 API helper。
- `apps/web/src/app/router.tsx`：新增 `/review` route。
- `apps/web/src/App.tsx`：新增“审核”导航。
- `apps/web/src/features/graph/EntityPanel.tsx`：新增“加入审核”入口并显示审核状态。
- `apps/web/src/features/graph/GraphPage.test.tsx`：覆盖加入审核入口。

E2E 和文档：

- `tests/e2e/review.spec.ts`
- `README.md`
- `docs/superpowers/plans/2026-07-07-xiaoao-jianghu-phase-3-review-quality.md`

---

### Task 1: 审核数据模型、仓储与幂等规则扫描

**Files:**
- Create: `apps/api/src/app/review/__init__.py`
- Create: `apps/api/src/app/review/models.py`
- Create: `apps/api/src/app/review/repository.py`
- Create: `apps/api/src/app/review/rules.py`
- Test: `apps/api/tests/review/test_repository.py`
- Test: `apps/api/tests/review/test_rules.py`

**Interfaces:**
- Consumes: `Project` SQLAlchemy base from `apps/api/src/app/projects/models.py`.
- Produces:
  - `ReviewItemType`, `ReviewItemStatus`, `ReviewSource`, `ReviewActionType`
  - `ReviewItemCreate`
  - `ReviewRepository.create_item_once(project_id: str, item: ReviewItemCreate) -> ReviewItemRead`
  - `ReviewRepository.list_items(project_id: str, status: ReviewItemStatus | None, item_type: ReviewItemType | None, limit: int, cursor: str | None) -> list[ReviewItemRead]`
  - `RuleScanner.scan_candidates(project_id: str, facts: list[FactCandidate], entities: list[dict[str, Any]]) -> list[ReviewItemCreate]`

- [x] **Step 1: Write failing repository tests**

Create `apps/api/tests/review/test_repository.py`:

```python
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
    repo.create_item_once("project-a", ReviewItemCreate(
        item_type=ReviewItemType.FACT,
        source=ReviewSource.RULE,
        reason_code="LOW_CONFIDENCE_FACT",
        target={"fact_id": "fact-1"},
        evidence_ids=[],
        fingerprint="fact:fact-1",
        severity=10,
    ))
    repo.create_item_once("project-a", ReviewItemCreate(
        item_type=ReviewItemType.DUPLICATE_ENTITY,
        source=ReviewSource.RULE,
        reason_code="POSSIBLE_DUPLICATE_ENTITY",
        target={"source_entity_id": "e-1", "target_entity_id": "e-2"},
        evidence_ids=[],
        fingerprint="entity:e-1:e-2",
        severity=30,
    ))

    rows = repo.list_items(
        "project-a",
        status=ReviewItemStatus.OPEN,
        item_type=ReviewItemType.DUPLICATE_ENTITY,
        limit=10,
        cursor=None,
    )

    assert [row.reason_code for row in rows] == ["POSSIBLE_DUPLICATE_ENTITY"]
```

- [x] **Step 2: Run repository tests and confirm failure**

Run: `.venv/bin/python -m pytest apps/api/tests/review/test_repository.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.review'`.

- [x] **Step 3: Implement review models and repository**

Create `apps/api/src/app/review/__init__.py` as an empty package file.

Create `apps/api/src/app/review/models.py`:

```python
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

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: f"review-{uuid4().hex}")
    project_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ReviewItemStatus.OPEN.value, index=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    fingerprint: Mapped[str] = mapped_column(String(300), nullable=False)
    severity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReviewAction(Base):
    __tablename__ = "review_actions"
    __table_args__ = (
        UniqueConstraint("project_id", "item_id", "action_type", "idempotency_key", name="uq_review_action_idempotency"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: f"action-{uuid4().hex}")
    project_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    item_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(40), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(120), nullable=False, default="local_reviewer")
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)


class QualitySnapshot(Base):
    __tablename__ = "quality_snapshots"

    id: Mapped[str] = mapped_column(String(80), primary_key=True, default=lambda: f"quality-{uuid4().hex}")
    project_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)


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
```

Create `apps/api/src/app/review/repository.py`:

```python
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
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
        rows = session_rows(self.session_factory, statement.order_by(ReviewItem.severity.desc(), ReviewItem.id).limit(limit))
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
            row = session.scalar(select(ReviewItem).where(ReviewItem.project_id == project_id, ReviewItem.id == item_id))
            return self._item(row) if row else None

    def resolve_item(self, project_id: str, item_id: str) -> ReviewItemRead:
        with self.session_factory() as session:
            row = session.scalar(select(ReviewItem).where(ReviewItem.project_id == project_id, ReviewItem.id == item_id))
            if row is None:
                raise ValueError("review_item_not_found")
            row.status = ReviewItemStatus.RESOLVED.value
            row.resolved_at = datetime.now(UTC)
            session.commit()
            session.refresh(row)
            return self._item(row)

    def dismiss_item(self, project_id: str, item_id: str) -> ReviewItemRead:
        with self.session_factory() as session:
            row = session.scalar(select(ReviewItem).where(ReviewItem.project_id == project_id, ReviewItem.id == item_id))
            if row is None:
                raise ValueError("review_item_not_found")
            row.status = ReviewItemStatus.DISMISSED.value
            row.resolved_at = datetime.now(UTC)
            session.commit()
            session.refresh(row)
            return self._item(row)

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

    def list_actions(self, project_id: str, limit: int, cursor: str | None) -> list[ReviewActionRead]:
        statement = select(ReviewAction).where(ReviewAction.project_id == project_id)
        if cursor:
            statement = statement.where(ReviewAction.id > cursor)
        rows = session_rows(self.session_factory, statement.order_by(ReviewAction.created_at.desc(), ReviewAction.id).limit(limit))
        return [self._action(row) for row in rows]

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


def session_rows(session_factory: sessionmaker, statement):
    with session_factory() as session:
        return list(session.scalars(statement))
```

- [x] **Step 4: Run repository tests**

Run: `.venv/bin/python -m pytest apps/api/tests/review/test_repository.py -v`

Expected: PASS.

- [x] **Step 5: Write failing rule scanner tests**

Create `apps/api/tests/review/test_rules.py`:

```python
from app.review.models import ReviewItemType
from app.review.rules import FactCandidate, RuleScanner


def test_rule_scanner_flags_low_confidence_missing_evidence_and_duplicates():
    scanner = RuleScanner(low_confidence_threshold=0.65)
    items = scanner.scan_candidates(
        project_id="project-a",
        facts=[
            FactCandidate(
                id="fact-low",
                type="ALLY_OF",
                source_id="linghu",
                target_id="ren",
                confidence=0.4,
                evidence_ids=["ev-1"],
                source_type="Person",
                target_type="Person",
            ),
            FactCandidate(
                id="fact-no-evidence",
                type="MASTER_OF",
                source_id="feng",
                target_id="linghu",
                confidence=0.9,
                evidence_ids=[],
                source_type="Person",
                target_type="Person",
            ),
        ],
        entities=[
            {"id": "e-1", "name": "令狐冲", "aliases": ["令狐少侠"], "type": "Person"},
            {"id": "e-2", "name": "令狐冲", "aliases": [], "type": "Person"},
        ],
    )

    assert {item.reason_code for item in items} >= {
        "LOW_CONFIDENCE_FACT",
        "MISSING_EVIDENCE",
        "POSSIBLE_DUPLICATE_ENTITY",
    }
    duplicate = next(item for item in items if item.reason_code == "POSSIBLE_DUPLICATE_ENTITY")
    assert duplicate.item_type == ReviewItemType.DUPLICATE_ENTITY
```

- [x] **Step 6: Run rule scanner test and confirm failure**

Run: `.venv/bin/python -m pytest apps/api/tests/review/test_rules.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.review.rules'`.

- [x] **Step 7: Implement deterministic rule scanner**

Create `apps/api/src/app/review/rules.py`:

```python
from dataclasses import dataclass
from typing import Any

from app.ontology.catalog import relation_by_id
from app.review.models import ReviewItemCreate, ReviewItemType, ReviewSource


@dataclass(frozen=True)
class FactCandidate:
    id: str
    type: str
    source_id: str
    target_id: str
    confidence: float
    evidence_ids: list[str]
    source_type: str
    target_type: str


class RuleScanner:
    def __init__(self, low_confidence_threshold: float = 0.65) -> None:
        self.low_confidence_threshold = low_confidence_threshold

    def scan_candidates(
        self,
        project_id: str,
        facts: list[FactCandidate],
        entities: list[dict[str, Any]],
    ) -> list[ReviewItemCreate]:
        items: list[ReviewItemCreate] = []
        for fact in facts:
            if fact.confidence < self.low_confidence_threshold:
                items.append(self._fact_item(fact, "LOW_CONFIDENCE_FACT", 40))
            if not fact.evidence_ids:
                items.append(self._fact_item(fact, "MISSING_EVIDENCE", 70))
            relation = relation_by_id(fact.type)
            if relation and (fact.source_type not in relation.source_types or fact.target_type not in relation.target_types):
                items.append(self._fact_item(fact, "ONTOLOGY_VIOLATION", 95))
        items.extend(self._duplicate_entity_items(entities))
        return items

    def _fact_item(self, fact: FactCandidate, reason_code: str, severity: int) -> ReviewItemCreate:
        return ReviewItemCreate(
            item_type=ReviewItemType.FACT,
            source=ReviewSource.RULE,
            reason_code=reason_code,
            target={"fact_id": fact.id},
            evidence_ids=fact.evidence_ids,
            fingerprint=f"fact:{fact.id}:{reason_code}",
            severity=severity,
        )

    def _duplicate_entity_items(self, entities: list[dict[str, Any]]) -> list[ReviewItemCreate]:
        by_name: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for entity in entities:
            by_name.setdefault((entity["type"], entity["name"].strip().lower()), []).append(entity)
        items: list[ReviewItemCreate] = []
        for (_, _), group in by_name.items():
            if len(group) < 2:
                continue
            source, target = sorted(group, key=lambda row: row["id"])[:2]
            items.append(
                ReviewItemCreate(
                    item_type=ReviewItemType.DUPLICATE_ENTITY,
                    source=ReviewSource.RULE,
                    reason_code="POSSIBLE_DUPLICATE_ENTITY",
                    target={"source_entity_id": source["id"], "target_entity_id": target["id"]},
                    evidence_ids=[],
                    fingerprint=f"duplicate:{source['id']}:{target['id']}",
                    severity=60,
                )
            )
        return items
```

Add this helper to `apps/api/src/app/ontology/catalog.py`:

```python
def relation_by_id(relation_id: str) -> Relation | None:
    return next((item for item in CATALOG.relation_types if item.id == relation_id), None)
```

- [x] **Step 8: Run review model and rule tests**

Run: `.venv/bin/python -m pytest apps/api/tests/review/test_repository.py apps/api/tests/review/test_rules.py -v`

Expected: PASS.

- [x] **Step 9: Commit**

```bash
git add apps/api/src/app/review apps/api/src/app/ontology/catalog.py apps/api/tests/review/test_repository.py apps/api/tests/review/test_rules.py
git commit -m "feat: add review queue models and rules"
```

---

### Task 2: Neo4j 审核状态写入与默认图谱过滤

**Files:**
- Create: `apps/api/src/app/review/graph.py`
- Modify: `apps/api/src/app/graph/repository.py`
- Modify: `apps/api/src/app/graph/models.py`
- Test: `apps/api/tests/graph/test_review_filters.py`

**Interfaces:**
- Consumes: existing `Neo4jGraphRepository`.
- Produces:
  - `ReviewGraphRepository.accept_fact(project_id: str, fact_id: str) -> None`
  - `ReviewGraphRepository.reject_fact(project_id: str, fact_id: str) -> None`
  - `ReviewGraphRepository.merge_entities(project_id: str, source_entity_id: str, target_entity_id: str) -> None`
  - `ReviewGraphRepository.split_alias(project_id: str, source_entity_id: str, alias: str, target_entity_id: str | None) -> str`
  - `ReviewGraphRepository.review_candidates(project_id: str) -> ReviewGraphSnapshot`

- [x] **Step 1: Write failing graph filter tests**

Create `apps/api/tests/graph/test_review_filters.py`:

```python
import pytest

from app.graph.importer import GraphImporter
from app.graph.models import ChapterRecord, EntityRecord, EvidenceRecord, FactRecord, GraphDocument, ProjectRecord
from app.graph.neo4j import Neo4jGraphWriter
from app.graph.repository import Neo4jGraphRepository
from app.ontology.models import EntityType, RelationType
from app.review.graph import ReviewGraphRepository
from app.settings import Settings


pytestmark = pytest.mark.skipif(
    not Settings().neo4j_uri,
    reason="Neo4j integration requires configured Neo4j",
)


def document() -> GraphDocument:
    return GraphDocument(
        project=ProjectRecord(id="review-filter", title="审核过滤测试"),
        chapters=[ChapterRecord(id="c1", number=1, title="第一章")],
        entities=[
            EntityRecord(id="linghu", type=EntityType.PERSON, name="令狐冲"),
            EntityRecord(id="yue", type=EntityType.PERSON, name="岳不群"),
        ],
        facts=[
            FactRecord(
                id="fact-master",
                type=RelationType.MASTER_OF,
                source_id="yue",
                target_id="linghu",
                evidence_ids=["ev1"],
                confidence=0.4,
            )
        ],
        evidence=[EvidenceRecord(id="ev1", chapter_id="c1", start_offset=0, end_offset=4, quote="岳不群传剑", text_hash="h")],
    )


def test_rejected_fact_is_hidden_from_default_graph(settings: Settings):
    writer = Neo4jGraphWriter.from_settings(settings)
    GraphImporter(writer).import_document(document())
    graph = Neo4jGraphRepository.from_settings(settings)
    review = ReviewGraphRepository.from_settings(settings)

    before = graph.entity_detail("review-filter", "linghu")
    assert any(row["id"] == "fact-master" for row in before["rows"])

    review.reject_fact("review-filter", "fact-master")

    after = graph.entity_detail("review-filter", "linghu")
    assert all(row["id"] != "fact-master" for row in after["rows"])
```

- [x] **Step 2: Run graph filter test and confirm failure**

Run: `RUN_NEO4J_INTEGRATION=1 .venv/bin/python -m pytest apps/api/tests/graph/test_review_filters.py -v`

Expected: FAIL because `app.review.graph` does not exist or repository does not filter rejected facts.

- [x] **Step 3: Implement ReviewGraphRepository**

Create `apps/api/src/app/review/graph.py`:

```python
from dataclasses import dataclass
from typing import Any

from neo4j import Driver, GraphDatabase

from app.review.rules import FactCandidate
from app.settings import Settings


@dataclass(frozen=True)
class ReviewGraphSnapshot:
    facts: list[FactCandidate]
    entities: list[dict[str, Any]]


class ReviewGraphRepository:
    def __init__(self, driver: Driver) -> None:
        self.driver = driver

    @classmethod
    def from_settings(cls, settings: Settings) -> "ReviewGraphRepository":
        return cls(GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)))

    def accept_fact(self, project_id: str, fact_id: str) -> None:
        self._run(
            """
            MATCH (fact:Fact {project_id: $project_id, id: $fact_id})
            SET fact.review_status = 'ACCEPTED'
            WITH fact
            OPTIONAL MATCH ()-[related:RELATED {project_id: $project_id, id: $fact_id}]->()
            SET related.review_status = 'ACCEPTED'
            """,
            project_id=project_id,
            fact_id=fact_id,
        )

    def reject_fact(self, project_id: str, fact_id: str) -> None:
        self._run(
            """
            MATCH (fact:Fact {project_id: $project_id, id: $fact_id})
            SET fact.review_status = 'REJECTED'
            WITH fact
            OPTIONAL MATCH ()-[related:RELATED {project_id: $project_id, id: $fact_id}]->()
            SET related.review_status = 'REJECTED'
            """,
            project_id=project_id,
            fact_id=fact_id,
        )

    def merge_entities(self, project_id: str, source_entity_id: str, target_entity_id: str) -> None:
        self._run(
            """
            MATCH (source:Entity {project_id: $project_id, id: $source_entity_id})
            MATCH (target:Entity {project_id: $project_id, id: $target_entity_id})
            SET source.review_status = 'MERGED',
                source.merged_into = target.id,
                target.review_status = coalesce(target.review_status, 'ACCEPTED'),
                target.aliases = coalesce(target.aliases, []) + coalesce(source.aliases, []) + [source.name]
            WITH source, target
            MATCH (fact:Fact {project_id: $project_id})-[:SOURCE|TARGET]->(source)
            SET fact.review_status = coalesce(fact.review_status, 'ACCEPTED')
            WITH fact
            OPTIONAL MATCH ()-[related:RELATED {project_id: $project_id, id: fact.id}]->()
            SET related.review_status = coalesce(related.review_status, 'ACCEPTED')
            """,
            project_id=project_id,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
        )

    def split_alias(self, project_id: str, source_entity_id: str, alias: str, target_entity_id: str | None) -> str:
        target_id = target_entity_id or f"{source_entity_id}__alias__{alias}"
        self._run(
            """
            MATCH (source:Entity {project_id: $project_id, id: $source_entity_id})
            SET source.aliases = [a IN coalesce(source.aliases, []) WHERE a <> $alias],
                source.review_status = 'SPLIT_SOURCE'
            MERGE (target:Entity {project_id: $project_id, id: $target_id})
            ON CREATE SET target.name = $alias, target.type = source.type, target.aliases = [], target.description = '', target.review_status = 'ACCEPTED'
            ON MATCH SET target.review_status = coalesce(target.review_status, 'ACCEPTED')
            """,
            project_id=project_id,
            source_entity_id=source_entity_id,
            alias=alias,
            target_id=target_id,
        )
        return target_id

    def review_candidates(self, project_id: str) -> ReviewGraphSnapshot:
        statement = """
        MATCH (fact:Fact {project_id: $project_id})
        OPTIONAL MATCH (fact)-[:SOURCE]->(source:Entity)
        OPTIONAL MATCH (fact)-[:TARGET]->(target:Entity)
        OPTIONAL MATCH (fact)-[:EVIDENCED_BY]->(evidence:Evidence)
        WITH fact, source, target, collect(evidence.id) AS evidence_ids
        RETURN collect({
            id: fact.id, type: fact.type, source_id: source.id, target_id: target.id,
            confidence: coalesce(fact.confidence, 1.0), evidence_ids: evidence_ids,
            source_type: source.type, target_type: target.type
        }) AS facts
        """
        with self.driver.session() as session:
            record = session.run(statement, project_id=project_id).single()
            fact_rows = record["facts"] if record else []
            entity_rows = session.run(
                "MATCH (entity:Entity {project_id: $project_id}) RETURN properties(entity) AS entity",
                project_id=project_id,
            )
            return ReviewGraphSnapshot(
                facts=[FactCandidate(**row) for row in fact_rows if row["id"]],
                entities=[dict(row["entity"]) for row in entity_rows],
            )

    def _run(self, statement: str, **parameters: Any) -> None:
        with self.driver.session() as session:
            session.run(statement, **parameters).consume()
```

- [x] **Step 4: Filter rejected facts and merged entities in graph repository**

Modify every Cypher query in `apps/api/src/app/graph/repository.py` that returns default graph data:

```cypher
AND coalesce(n.review_status, 'ACCEPTED') <> 'MERGED'
```

For relationships/facts, add:

```cypher
AND coalesce(fact.review_status, 'ACCEPTED') <> 'REJECTED'
```

For `neighborhood`, add relationship filtering:

```cypher
WHERE all(r IN rels WHERE coalesce(r.review_status, 'ACCEPTED') <> 'REJECTED'
    AND ($from_chapter IS NULL OR r.to_chapter IS NULL OR r.to_chapter >= $from_chapter)
    AND ($to_chapter IS NULL OR r.from_chapter IS NULL OR r.from_chapter <= $to_chapter))
```

If current graph edges are `RELATED` relationships while facts are separate `Fact` nodes, keep both safe: set `review_status` on both `Fact` nodes and corresponding `RELATED` relationships when applying review actions.

- [x] **Step 5: Run graph filter tests**

Run: `RUN_NEO4J_INTEGRATION=1 .venv/bin/python -m pytest apps/api/tests/graph/test_review_filters.py apps/api/tests/graph/test_live_api.py apps/api/tests/graph/test_service.py -v`

Expected: PASS.

- [x] **Step 6: Commit**

```bash
git add apps/api/src/app/review/graph.py apps/api/src/app/graph/repository.py apps/api/src/app/graph/models.py apps/api/tests/graph/test_review_filters.py
git commit -m "feat: apply review status to graph queries"
```

---

### Task 3: 事实接受/拒绝动作、审计日志与问答过滤

**Files:**
- Create/Modify: `apps/api/src/app/review/service.py`
- Modify: `apps/api/src/app/qa/service.py`
- Test: `apps/api/tests/review/test_service_facts.py`
- Test: `apps/api/tests/qa/test_review_filters.py`

**Interfaces:**
- Consumes: `ReviewRepository`, `ReviewGraphRepository`.
- Produces:
  - `ReviewService.apply_action(project_id: str, item_id: str, request: ReviewActionRequest) -> ReviewActionResult`
  - `ReviewActionRequest(action_type: ReviewActionType, payload: dict[str, Any], idempotency_key: str | None = None)`
  - `ReviewActionResult(item: ReviewItemRead, action: ReviewActionRead)`

- [x] **Step 1: Write failing fact action tests**

Create `apps/api/tests/review/test_service_facts.py`:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.projects.models import Base
from app.review.models import ReviewActionType, ReviewItemStatus, ReviewItemType, ReviewSource
from app.review.repository import ReviewItemCreate, ReviewRepository
from app.review.service import ReviewActionRequest, ReviewService


class FakeReviewGraph:
    def __init__(self):
        self.accepted: list[str] = []
        self.rejected: list[str] = []

    def accept_fact(self, project_id: str, fact_id: str) -> None:
        self.accepted.append(f"{project_id}:{fact_id}")

    def reject_fact(self, project_id: str, fact_id: str) -> None:
        self.rejected.append(f"{project_id}:{fact_id}")


def service():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repo = ReviewRepository(sessionmaker(engine))
    graph = FakeReviewGraph()
    return ReviewService(repo, graph), repo, graph


def test_accept_fact_records_audit_and_resolves_item():
    svc, repo, graph = service()
    item = repo.create_item_once("project-a", ReviewItemCreate(
        item_type=ReviewItemType.FACT,
        source=ReviewSource.RULE,
        reason_code="LOW_CONFIDENCE_FACT",
        target={"fact_id": "fact-1"},
        evidence_ids=["ev-1"],
        fingerprint="fact:fact-1:LOW_CONFIDENCE_FACT",
        severity=40,
    ))

    result = svc.apply_action("project-a", item.id, ReviewActionRequest(
        action_type=ReviewActionType.ACCEPT_FACT,
        payload={"fact_id": "fact-1"},
        idempotency_key="accept-fact-1",
    ))

    assert result.item.status == ReviewItemStatus.RESOLVED
    assert result.action.reviewer == "local_reviewer"
    assert graph.accepted == ["project-a:fact-1"]


def test_reject_fact_is_idempotent():
    svc, repo, graph = service()
    item = repo.create_item_once("project-a", ReviewItemCreate(
        item_type=ReviewItemType.FACT,
        source=ReviewSource.RULE,
        reason_code="LOW_CONFIDENCE_FACT",
        target={"fact_id": "fact-1"},
        evidence_ids=[],
        fingerprint="fact:fact-1",
        severity=40,
    ))
    request = ReviewActionRequest(
        action_type=ReviewActionType.REJECT_FACT,
        payload={"fact_id": "fact-1"},
        idempotency_key="reject-fact-1",
    )

    first = svc.apply_action("project-a", item.id, request)
    second = svc.apply_action("project-a", item.id, request)

    assert first.action.id == second.action.id
    assert graph.rejected == ["project-a:fact-1", "project-a:fact-1"]
```

- [x] **Step 2: Run fact action tests and confirm failure**

Run: `.venv/bin/python -m pytest apps/api/tests/review/test_service_facts.py -v`

Expected: FAIL because `app.review.service` does not exist.

- [x] **Step 3: Implement fact action service**

Create or modify `apps/api/src/app/review/service.py`:

```python
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from app.review.models import ReviewActionRead, ReviewActionType, ReviewItemRead
from app.review.repository import ReviewRepository


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

    def apply_action(self, project_id: str, item_id: str, request: ReviewActionRequest) -> ReviewActionResult:
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
        resolved = self.repository.dismiss_item(project_id, item_id) if request.action_type == ReviewActionType.DISMISS_ITEM else self.repository.resolve_item(project_id, item_id)
        return ReviewActionResult(item=resolved, action=action)

    def _payload_value(self, payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"missing_payload:{key}")
        return value
```

- [x] **Step 4: Run fact action tests**

Run: `.venv/bin/python -m pytest apps/api/tests/review/test_service_facts.py apps/api/tests/review/test_repository.py -v`

Expected: PASS.

- [x] **Step 5: Write QA filtering regression test**

Create `apps/api/tests/qa/test_review_filters.py`:

```python
from app.qa.service import NO_FACTS, QaService


class Repository:
    def search(self, project_id, query, types, limit):
        return [{"id": "linghu", "name": "令狐冲", "description": "华山弟子"}]

    def entity_detail(self, project_id, entity_id):
        if entity_id == "linghu":
            return {
                "entity": {"id": "linghu", "name": "令狐冲"},
                "rows": [
                    {"id": "rejected", "type": "MASTER_OF", "source_id": "yue", "target_id": "linghu", "review_status": "REJECTED", "evidence": None}
                ],
            }
        return {"entity": {"id": entity_id, "name": "岳不群"}, "rows": []}


def test_qa_ignores_rejected_facts_even_if_repository_returns_them():
    response = QaService(Repository()).ask("project-a", "令狐冲的师父是谁")

    assert response.answer == NO_FACTS
```

- [x] **Step 6: Run QA filtering test and confirm failure**

Run: `.venv/bin/python -m pytest apps/api/tests/qa/test_review_filters.py -v`

Expected: FAIL because `QaService` does not explicitly ignore rejected rows if a repository returns them.

- [x] **Step 7: Harden QA service against rejected rows**

Modify `apps/api/src/app/qa/service.py` in the loop over `detail["rows"]`:

```python
        for row in detail["rows"]:
            if row.get("review_status") == "REJECTED":
                continue
            if row.get("type") != template.relation:
                continue
```

- [x] **Step 8: Run QA and review tests**

Run: `.venv/bin/python -m pytest apps/api/tests/review/test_service_facts.py apps/api/tests/qa/test_review_filters.py apps/api/tests/qa/test_service.py -v`

Expected: PASS.

- [x] **Step 9: Commit**

```bash
git add apps/api/src/app/review/service.py apps/api/src/app/qa/service.py apps/api/tests/review/test_service_facts.py apps/api/tests/qa/test_review_filters.py
git commit -m "feat: review fact decisions with audit"
```

---

### Task 4: 实体合并与别名拆出动作

**Files:**
- Modify: `apps/api/src/app/review/service.py`
- Modify: `apps/api/src/app/review/graph.py`
- Test: `apps/api/tests/review/test_service_entities.py`

**Interfaces:**
- Consumes: `ReviewService.apply_action()`.
- Produces action payloads:
  - `merge_entities`: `{"source_entity_id": str, "target_entity_id": str}`
  - `split_alias`: `{"source_entity_id": str, "alias": str, "target_entity_id": str | None}`

- [x] **Step 1: Write failing entity action tests**

Create `apps/api/tests/review/test_service_entities.py`:

```python
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

    def merge_entities(self, project_id: str, source_entity_id: str, target_entity_id: str) -> None:
        self.merges.append((project_id, source_entity_id, target_entity_id))

    def split_alias(self, project_id: str, source_entity_id: str, alias: str, target_entity_id: str | None) -> str:
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
    item = repo.create_item_once("project-a", ReviewItemCreate(
        item_type=ReviewItemType.DUPLICATE_ENTITY,
        source=ReviewSource.RULE,
        reason_code="POSSIBLE_DUPLICATE_ENTITY",
        target={"source_entity_id": "e-1", "target_entity_id": "e-2"},
        fingerprint="duplicate:e-1:e-2",
        severity=60,
    ))

    result = svc.apply_action("project-a", item.id, ReviewActionRequest(
        action_type=ReviewActionType.MERGE_ENTITIES,
        payload={"source_entity_id": "e-1", "target_entity_id": "e-2"},
        idempotency_key="merge-e-1-e-2",
    ))

    assert graph.merges == [("project-a", "e-1", "e-2")]
    assert result.action.payload["target_entity_id"] == "e-2"


def test_split_alias_returns_created_entity_id_in_audit_payload():
    svc, repo, graph = service()
    item = repo.create_item_once("project-a", ReviewItemCreate(
        item_type=ReviewItemType.ALIAS_SPLIT,
        source=ReviewSource.RULE,
        reason_code="ALIAS_SPLIT_CANDIDATE",
        target={"source_entity_id": "e-1", "alias": "风清扬"},
        fingerprint="alias:e-1:风清扬",
        severity=50,
    ))

    result = svc.apply_action("project-a", item.id, ReviewActionRequest(
        action_type=ReviewActionType.SPLIT_ALIAS,
        payload={"source_entity_id": "e-1", "alias": "风清扬"},
        idempotency_key="split-e-1-feng",
    ))

    assert graph.splits == [("project-a", "e-1", "风清扬", None)]
    assert result.action.payload["created_entity_id"] == "e-1__alias__风清扬"
```

- [x] **Step 2: Run entity action tests and confirm failure**

Run: `.venv/bin/python -m pytest apps/api/tests/review/test_service_entities.py -v`

Expected: FAIL with `unsupported_action:merge_entities`.

- [x] **Step 3: Extend ReviewService for merge and split**

Modify `apps/api/src/app/review/service.py`:

```python
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
            created_entity_id = self.graph.split_alias(project_id, source_entity_id, alias, target_entity_id)
            request.payload["created_entity_id"] = created_entity_id
```

Keep the `DISMISS_ITEM` branch and unsupported branch after these cases.

- [x] **Step 4: Run entity and fact service tests**

Run: `.venv/bin/python -m pytest apps/api/tests/review/test_service_facts.py apps/api/tests/review/test_service_entities.py -v`

Expected: PASS.

- [x] **Step 5: Add graph-level merge/split integration checks**

Extend `apps/api/tests/graph/test_review_filters.py` with:

```python
def test_merged_entity_is_hidden_from_search(settings: Settings):
    writer = Neo4jGraphWriter.from_settings(settings)
    GraphImporter(writer).import_document(document())
    graph = Neo4jGraphRepository.from_settings(settings)
    review = ReviewGraphRepository.from_settings(settings)

    review.merge_entities("review-filter", "linghu", "yue")

    results = graph.search("review-filter", "令狐冲", [], 10)
    assert all(row["id"] != "linghu" for row in results)


def test_split_alias_removes_alias_from_source(settings: Settings):
    writer = Neo4jGraphWriter.from_settings(settings)
    GraphImporter(writer).import_document(document())
    review = ReviewGraphRepository.from_settings(settings)
    graph = Neo4jGraphRepository.from_settings(settings)

    review.split_alias("review-filter", "linghu", "冲儿", None)

    detail = graph.entity_detail("review-filter", "linghu")
    assert "冲儿" not in detail["entity"].get("aliases", [])
```

If the imported fixture does not include alias `冲儿`, adjust the fixture entity to include it.

- [x] **Step 6: Run graph integration checks**

Run: `RUN_NEO4J_INTEGRATION=1 .venv/bin/python -m pytest apps/api/tests/graph/test_review_filters.py -v`

Expected: PASS.

- [x] **Step 7: Commit**

```bash
git add apps/api/src/app/review/service.py apps/api/src/app/review/graph.py apps/api/tests/review/test_service_entities.py apps/api/tests/graph/test_review_filters.py
git commit -m "feat: review entity merge and alias split actions"
```

---

### Task 5: Review API、summary、audit 与 scan 编排

**Files:**
- Create: `apps/api/src/app/review/router.py`
- Modify: `apps/api/src/app/review/service.py`
- Modify: `apps/api/src/app/main.py`
- Test: `apps/api/tests/review/test_router.py`

**Interfaces:**
- Consumes: `ReviewRepository`, `ReviewGraphRepository`, `RuleScanner`.
- Produces REST endpoints:
  - `GET /api/projects/{project_id}/review/summary`
  - `GET /api/projects/{project_id}/review/items`
  - `POST /api/projects/{project_id}/review/items`
  - `POST /api/projects/{project_id}/review/items/{item_id}/actions`
  - `GET /api/projects/{project_id}/review/audit`
  - `POST /api/projects/{project_id}/review/scan`

- [x] **Step 1: Write failing router tests**

Create `apps/api/tests/review/test_router.py`:

```python
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_review_scan_and_items_endpoint():
    response = client.post("/api/projects/xiaoao/review/scan")
    assert response.status_code == 200
    body = response.json()
    assert "created_items" in body

    items = client.get("/api/projects/xiaoao/review/items?status=OPEN&limit=20")
    assert items.status_code == 200
    assert isinstance(items.json()["items"], list)


def test_manual_review_item_and_action_endpoint():
    create = client.post("/api/projects/xiaoao/review/items", json={
        "item_type": "FACT",
        "reason_code": "MANUAL_REVIEW",
        "target": {"fact_id": "manual-fact"},
        "evidence_ids": [],
        "fingerprint": "manual:manual-fact",
        "severity": 10,
    })
    assert create.status_code == 200
    item_id = create.json()["id"]

    action = client.post(f"/api/projects/xiaoao/review/items/{item_id}/actions", json={
        "action_type": "dismiss_item",
        "payload": {},
        "idempotency_key": "dismiss-manual-fact",
    })
    assert action.status_code == 200
    assert action.json()["item"]["status"] == "DISMISSED"
```

- [x] **Step 2: Run router tests and confirm failure**

Run: `.venv/bin/python -m pytest apps/api/tests/review/test_router.py -v`

Expected: FAIL with 404 for review endpoints.

- [x] **Step 3: Add summary, scan and audit service methods**

Modify `apps/api/src/app/review/service.py`:

```python
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
```

Do not create a second `ReviewService` class if Task 3 already created it. Merge these methods into the existing class and add imports for `RuleScanner`, `ReviewSummary` and `ReviewScanResult`.

- [x] **Step 4: Implement review router**

Create `apps/api/src/app/review/router.py`:

```python
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.projects.models import Base
from app.review.graph import ReviewGraphRepository
from app.review.models import ReviewItemCreate, ReviewItemStatus, ReviewItemType, ReviewSource
from app.review.repository import ReviewRepository
from app.review.service import ReviewActionRequest, ReviewService
from app.settings import Settings

router = APIRouter(prefix="/api/projects/{project_id}/review", tags=["review"])


class ManualReviewItemRequest(BaseModel):
    item_type: ReviewItemType
    reason_code: str = Field(min_length=1)
    target: dict[str, str]
    evidence_ids: list[str] = Field(default_factory=list)
    fingerprint: str = Field(min_length=1)
    severity: int = Field(default=10, ge=0, le=100)


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
    return {"items": service().repository.list_items(project_id, status, item_type, limit, cursor)}


@router.post("/items")
def create_item(project_id: str, item: ManualReviewItemRequest):
    return service().repository.create_item_once(
        project_id,
        ReviewItemCreate(source=ReviewSource.MANUAL, **item.model_dump()),
    )


@router.post("/items/{item_id}/actions")
def apply_action(project_id: str, item_id: str, request: ReviewActionRequest):
    try:
        return service().apply_action(project_id, item_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/audit")
def audit(project_id: str, limit: int = Query(default=50, ge=1, le=100), cursor: str | None = None):
    return {"actions": service().audit(project_id, limit=limit, cursor=cursor)}


@router.post("/scan")
def scan(project_id: str):
    return service().scan(project_id)
```

Modify `apps/api/src/app/main.py`:

```python
from app.review.router import router as review_router

app.include_router(review_router)
```

- [x] **Step 5: Run router tests**

Run: `.venv/bin/python -m pytest apps/api/tests/review/test_router.py apps/api/tests/test_health.py -v`

Expected: PASS.

- [x] **Step 6: Run all review backend tests**

Run: `RUN_NEO4J_INTEGRATION=1 .venv/bin/python -m pytest apps/api/tests/review apps/api/tests/graph/test_review_filters.py apps/api/tests/qa/test_review_filters.py -v`

Expected: PASS.

- [x] **Step 7: Commit**

```bash
git add apps/api/src/app/review apps/api/src/app/main.py apps/api/tests/review/test_router.py
git commit -m "feat: expose review workflow APIs"
```

---

### Task 6: 前端审核工作台和质量仪表盘

**Files:**
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/app/router.tsx`
- Modify: `apps/web/src/App.tsx`
- Create: `apps/web/src/features/review/ReviewPage.tsx`
- Create: `apps/web/src/features/review/ReviewSummary.tsx`
- Create: `apps/web/src/features/review/ReviewQueue.tsx`
- Create: `apps/web/src/features/review/ReviewDetail.tsx`
- Create: `apps/web/src/features/review/AuditDrawer.tsx`
- Test: `apps/web/src/features/review/ReviewPage.test.tsx`

**Interfaces:**
- Consumes review endpoints from Task 5.
- Produces route `/review`.

- [x] **Step 1: Write failing ReviewPage test**

Create `apps/web/src/features/review/ReviewPage.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ProjectProvider } from '../../app/ProjectContext'
import { ReviewPage } from './ReviewPage'

const fetchMock = vi.fn()

beforeEach(() => {
  global.fetch = fetchMock
})

afterEach(() => {
  vi.restoreAllMocks()
})

function json(data: unknown) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(data) } as Response)
}

function renderPage() {
  return render(
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient()}>
        <ProjectProvider>
          <ReviewPage />
        </ProjectProvider>
      </QueryClientProvider>
    </MemoryRouter>
  )
}

describe('ReviewPage', () => {
  it('shows quality summary, queue and applies a fact decision', async () => {
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/summary')) return json({ open_review_items: 1, accepted_facts: 2, rejected_facts: 0, pending_facts: 1, merged_entities: 0, split_aliases: 0, evidence_coverage: 0.8, review_completion_rate: 0.5, graph_fact_delta_before_after_review: 0 })
      if (url.includes('/items/') && url.includes('/actions')) return json({ item: { id: 'review-1', status: 'RESOLVED' }, action: { id: 'action-1' } })
      if (url.includes('/items')) return json({ items: [{ id: 'review-1', item_type: 'FACT', status: 'OPEN', reason_code: 'LOW_CONFIDENCE_FACT', target: { fact_id: 'fact-1' }, evidence_ids: ['ev-1'], severity: 40, source: 'rule' }] })
      if (url.includes('/audit')) return json({ actions: [] })
      return json({})
    })
    renderPage()

    expect(await screen.findByText('审核工作台')).toBeInTheDocument()
    expect(screen.getByText('待审核项')).toBeInTheDocument()
    expect(screen.getByText('LOW_CONFIDENCE_FACT')).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: '接受事实' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/review/items/review-1/actions'), expect.objectContaining({ method: 'POST' })))
  })
})
```

- [x] **Step 2: Run frontend test and confirm failure**

Run: `npm --prefix apps/web test -- ReviewPage --run`

Expected: FAIL because `ReviewPage` does not exist.

- [x] **Step 3: Add review API types**

Modify `apps/web/src/api/client.ts`:

```ts
export type ReviewSummary = {
  open_review_items: number
  accepted_facts: number
  rejected_facts: number
  pending_facts: number
  merged_entities: number
  split_aliases: number
  evidence_coverage: number
  review_completion_rate: number
  graph_fact_delta_before_after_review: number
}

export type ReviewItem = {
  id: string
  project_id?: string
  item_type: 'FACT' | 'DUPLICATE_ENTITY' | 'ALIAS_SPLIT'
  status: 'OPEN' | 'RESOLVED' | 'DISMISSED'
  source: 'rule' | 'model' | 'manual'
  reason_code: string
  target: Record<string, string>
  evidence_ids: string[]
  severity: number
}

export type ReviewActionRequest = {
  action_type: 'accept_fact' | 'reject_fact' | 'merge_entities' | 'split_alias' | 'dismiss_item'
  payload: Record<string, string>
  idempotency_key?: string
}

export type ReviewAction = { id: string; reviewer: string; action_type: string; payload: Record<string, string>; created_at: string }
```

- [x] **Step 4: Implement review components**

Create `apps/web/src/features/review/ReviewSummary.tsx`:

```tsx
import type { ReviewSummary as Summary } from '../../api/client'

export function ReviewSummary({ summary }: { summary: Summary }) {
  const metrics = [
    ['待审核项', summary.open_review_items],
    ['已接受事实', summary.accepted_facts],
    ['已拒绝事实', summary.rejected_facts],
    ['合并实体', summary.merged_entities],
    ['拆出别名', summary.split_aliases],
    ['证据覆盖率', `${Math.round(summary.evidence_coverage * 100)}%`],
  ]
  return <section className="quality-report"><p className="eyebrow">REVIEW QUALITY</p><h2>质量仪表盘</h2><div className="quality-metrics">{metrics.map(([label, value]) => <div key={label}><strong>{value}</strong><span>{label}</span></div>)}</div></section>
}
```

Create `apps/web/src/features/review/ReviewQueue.tsx`:

```tsx
import type { ReviewItem } from '../../api/client'

export function ReviewQueue({ items, selectedId, onSelect }: { items: ReviewItem[]; selectedId?: string; onSelect: (item: ReviewItem) => void }) {
  return <aside className="review-queue"><h2>审核队列</h2>{items.map(item => <button className={item.id === selectedId ? 'active' : ''} key={item.id} onClick={() => onSelect(item)}><b>{item.reason_code}</b><span>{item.item_type} · {item.source} · severity {item.severity}</span></button>)}</aside>
}
```

Create `apps/web/src/features/review/ReviewDetail.tsx`:

```tsx
import type { ReviewActionRequest, ReviewItem } from '../../api/client'

export function ReviewDetail({ item, onAction }: { item?: ReviewItem; onAction: (request: ReviewActionRequest) => void }) {
  if (!item) return <section className="review-detail"><h2>选择一个待审核项</h2></section>
  const factId = item.target.fact_id ?? ''
  return <section className="review-detail"><p className="eyebrow">{item.item_type}</p><h2>{item.reason_code}</h2><pre>{JSON.stringify(item.target, null, 2)}</pre><div className="review-actions">{item.item_type === 'FACT' && <><button onClick={() => onAction({ action_type: 'accept_fact', payload: { fact_id: factId }, idempotency_key: `accept-${item.id}` })}>接受事实</button><button onClick={() => onAction({ action_type: 'reject_fact', payload: { fact_id: factId }, idempotency_key: `reject-${item.id}` })}>拒绝事实</button></>}<button onClick={() => onAction({ action_type: 'dismiss_item', payload: {}, idempotency_key: `dismiss-${item.id}` })}>忽略</button></div></section>
}
```

Create `apps/web/src/features/review/AuditDrawer.tsx`:

```tsx
import type { ReviewAction } from '../../api/client'

export function AuditDrawer({ actions }: { actions: ReviewAction[] }) {
  return <aside className="audit-drawer"><h2>审计日志</h2>{actions.length === 0 ? <p>暂无审核动作</p> : actions.map(action => <article key={action.id}><b>{action.action_type}</b><span>{action.reviewer}</span></article>)}</aside>
}
```

Create `apps/web/src/features/review/ReviewPage.tsx`:

```tsx
import { useEffect, useMemo, useState } from 'react'

import { apiFetch, type ReviewAction, type ReviewActionRequest, type ReviewItem, type ReviewSummary as Summary } from '../../api/client'
import { useProject } from '../../app/ProjectContext'
import { AuditDrawer } from './AuditDrawer'
import { ReviewDetail } from './ReviewDetail'
import { ReviewQueue } from './ReviewQueue'
import { ReviewSummary } from './ReviewSummary'

const EMPTY_SUMMARY: Summary = { open_review_items: 0, accepted_facts: 0, rejected_facts: 0, pending_facts: 0, merged_entities: 0, split_aliases: 0, evidence_coverage: 0, review_completion_rate: 0, graph_fact_delta_before_after_review: 0 }

export function ReviewPage() {
  const { projectId } = useProject()
  const [summary, setSummary] = useState<Summary>(EMPTY_SUMMARY)
  const [items, setItems] = useState<ReviewItem[]>([])
  const [actions, setActions] = useState<ReviewAction[]>([])
  const [selectedId, setSelectedId] = useState<string>()
  const selected = useMemo(() => items.find(item => item.id === selectedId) ?? items[0], [items, selectedId])

  useEffect(() => {
    apiFetch<Summary>(`/api/projects/${projectId}/review/summary`).then(setSummary)
    apiFetch<{ items: ReviewItem[] }>(`/api/projects/${projectId}/review/items?status=OPEN&limit=50`).then(body => setItems(body.items))
    apiFetch<{ actions: ReviewAction[] }>(`/api/projects/${projectId}/review/audit?limit=20`).then(body => setActions(body.actions))
  }, [projectId])

  function applyAction(request: ReviewActionRequest) {
    if (!selected) return
    apiFetch(`/api/projects/${projectId}/review/items/${selected.id}/actions`, { method: 'POST', body: JSON.stringify(request) })
      .then(() => setItems(current => current.filter(item => item.id !== selected.id)))
  }

  return <section className="review-page"><header><p className="eyebrow">REVIEW · PHASE 3</p><h1>审核工作台</h1></header><ReviewSummary summary={summary} /><div className="review-workspace"><ReviewQueue items={items} selectedId={selected?.id} onSelect={item => setSelectedId(item.id)} /><ReviewDetail item={selected} onAction={applyAction} /><AuditDrawer actions={actions} /></div></section>
}
```

- [x] **Step 5: Wire route and navigation**

Modify `apps/web/src/app/router.tsx`:

```tsx
import { ReviewPage } from '../features/review/ReviewPage'

<Route path="/review" element={<ReviewPage />} />
```

Modify `apps/web/src/App.tsx` navigation links to include:

```tsx
<NavLink to="/review">审核</NavLink>
```

Use the existing `NavLink` style and placement pattern in `App.tsx`.

- [x] **Step 6: Run frontend review tests**

Run: `npm --prefix apps/web test -- ReviewPage --run`

Expected: PASS.

- [x] **Step 7: Run frontend suite**

Run: `npm --prefix apps/web test -- --run && npm --prefix apps/web run typecheck`

Expected: PASS.

- [x] **Step 8: Commit**

```bash
git add apps/web/src/api/client.ts apps/web/src/app/router.tsx apps/web/src/App.tsx apps/web/src/features/review
git commit -m "feat: add review quality workspace"
```

---

### Task 7: 图谱页手动加入审核与审核后查询回归

**Files:**
- Modify: `apps/web/src/features/graph/EntityPanel.tsx`
- Modify: `apps/web/src/features/graph/GraphPage.tsx`
- Modify: `apps/web/src/features/graph/GraphPage.test.tsx`
- Modify: `apps/api/tests/graph/test_router.py`

**Interfaces:**
- Consumes: `POST /api/projects/{project_id}/review/items`.
- Produces graph page manual review entry for facts and entities.

- [x] **Step 1: Write failing GraphPage manual review test**

Modify `apps/web/src/features/graph/GraphPage.test.tsx` by adding:

```tsx
it('adds a visible fact to the review queue', async () => {
  const user = userEvent.setup()
  fetchMock.mockImplementation((url: string, init?: RequestInit) => {
    if (url.includes('/api/entities/linghu')) return json({
      id: 'linghu',
      project_id: 'xiaoao',
      type: 'Person',
      name: '令狐冲',
      aliases: [],
      description: '华山弟子',
      facts: [{ id: 'fact-1', type: 'MASTER_OF', source_id: 'yue', target_id: 'linghu', evidence: [{ id: 'ev-1', chapter_id: 'c1', chapter_number: 1, chapter_title: '第一章', start_offset: 0, end_offset: 4, quote: '岳不群传剑' }] }],
    })
    if (url.includes('/api/graph/neighborhood')) return json({ nodes: [], edges: [] })
    if (url.includes('/api/projects/xiaoao/review/items') && init?.method === 'POST') return json({ id: 'review-1' })
    if (url.includes('/api/graph/search')) return json([{ id: 'linghu', project_id: 'xiaoao', type: 'Person', name: '令狐冲', aliases: [], description: '华山弟子' }])
    return json({})
  })
  renderGraphPage()

  await user.type(screen.getByRole('searchbox'), '令狐冲')
  await user.click(await screen.findByText('令狐冲'))
  await user.click(await screen.findByRole('button', { name: '加入审核' }))

  expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/api/projects/xiaoao/review/items'), expect.objectContaining({ method: 'POST' }))
})
```

Use the existing helpers in `GraphPage.test.tsx`; if helper names differ, adapt the test to the current file's patterns.

- [x] **Step 2: Run GraphPage test and confirm failure**

Run: `npm --prefix apps/web test -- GraphPage --run`

Expected: FAIL because `加入审核` button is missing.

- [x] **Step 3: Add manual review callback**

Modify `apps/web/src/features/graph/EntityPanel.tsx` props:

```tsx
export function EntityPanel({ detail, onClose, onReviewFact }: { detail?: EntityDetail; onClose: () => void; onReviewFact?: (factId: string) => void }) {
```

Inside each fact/evidence block, add:

```tsx
<button type="button" onClick={() => onReviewFact?.(fact.id)}>加入审核</button>
```

Modify `apps/web/src/features/graph/GraphPage.tsx`:

```tsx
function reviewFact(factId: string) {
  apiFetch(`/api/projects/${projectId}/review/items`, {
    method: 'POST',
    body: JSON.stringify({
      item_type: 'FACT',
      reason_code: 'MANUAL_REVIEW',
      target: { fact_id: factId },
      evidence_ids: [],
      fingerprint: `manual:${factId}`,
      severity: 10,
    }),
  }).catch((e: Error) => setError(e.message))
}

<EntityPanel detail={detail} onClose={() => setDetail(undefined)} onReviewFact={reviewFact} />
```

- [x] **Step 4: Run graph frontend tests**

Run: `npm --prefix apps/web test -- GraphPage --run`

Expected: PASS.

- [x] **Step 5: Add backend router regression for bounded graph filters**

Modify `apps/api/tests/graph/test_router.py` to assert rejected review status does not leak through router responses if fixture setup supports status mutation. Add a focused test around the repository/service boundary if router fixture does not use Neo4j.

Use this assertion shape:

```python
assert all(edge["id"] != "fact-rejected" for edge in response.json()["edges"])
```

- [x] **Step 6: Run graph and QA regression tests**

Run: `.venv/bin/python -m pytest apps/api/tests/graph apps/api/tests/qa -v`

Expected: PASS.

- [x] **Step 7: Commit**

```bash
git add apps/web/src/features/graph apps/api/tests/graph/test_router.py
git commit -m "feat: send graph facts to review"
```

---

### Task 8: E2E、README、验收命令与版本准备

**Files:**
- Create: `tests/e2e/review.spec.ts`
- Modify: `README.md`
- Modify: `Makefile` if `make verify` needs to include new review tests explicitly.
- Modify: `apps/api/pyproject.toml`
- Modify: `apps/web/package.json`
- Modify: `apps/web/package-lock.json`
- Modify: `tests/e2e/package.json`
- Modify: `tests/e2e/package-lock.json`

**Interfaces:**
- Consumes: all review APIs and `/review` page.
- Produces: full verification gate and version bump to `0.3.0`.

- [ ] **Step 1: Write E2E review workflow test**

Create `tests/e2e/review.spec.ts`:

```ts
import { test, expect } from '@playwright/test'

test('reviewer scans, accepts and sees audit trail', async ({ page }) => {
  await page.request.post('/api/projects/xiaoao/review/items', {
    data: {
      item_type: 'FACT',
      reason_code: 'MANUAL_REVIEW',
      target: { fact_id: 'e2e-review-fact' },
      evidence_ids: [],
      fingerprint: `manual:e2e-review-fact:${Date.now()}`,
      severity: 10,
    },
  })
  await page.goto('/review?project=xiaoao')
  await expect(page.getByRole('heading', { name: '审核工作台' })).toBeVisible()
  await expect(page.getByText('质量仪表盘')).toBeVisible()
  await expect(page.getByText('审核队列')).toBeVisible()

  const accept = page.getByRole('button', { name: '接受事实' })
  if (await accept.count()) {
    await accept.first().click()
    await expect(page.getByText('审计日志')).toBeVisible()
  }

  await page.goto('/graph?project=xiaoao')
  await expect(page.getByRole('heading', { name: '沿关系，游江湖' })).toBeVisible()
})
```

- [ ] **Step 2: Run E2E test and confirm failure before route/API exists**

Run: `npm --prefix tests/e2e test -- review.spec.ts`

Expected before full implementation: FAIL due missing `/review` route or review API.

- [ ] **Step 3: Add backend rule fixture for three review item types**

Extend `apps/api/tests/review/test_rules.py` with a deterministic fixture that produces `LOW_CONFIDENCE_FACT`, `MISSING_EVIDENCE`, and `POSSIBLE_DUPLICATE_ENTITY` in one scan. Do not alter production seed data for this requirement.

Acceptance check:

```python
def test_rule_scanner_produces_three_review_item_types():
    scanner = RuleScanner(low_confidence_threshold=0.65)
    items = scanner.scan_candidates(
        project_id="project-a",
        facts=[
            FactCandidate(id="fact-low", type="ALLY_OF", source_id="e-1", target_id="e-2", confidence=0.4, evidence_ids=["ev-1"], source_type="Person", target_type="Person"),
            FactCandidate(id="fact-missing", type="MASTER_OF", source_id="e-1", target_id="e-2", confidence=0.9, evidence_ids=[], source_type="Person", target_type="Person"),
        ],
        entities=[
            {"id": "e-1", "name": "令狐冲", "aliases": [], "type": "Person"},
            {"id": "e-2", "name": "令狐冲", "aliases": [], "type": "Person"},
        ],
    )
    assert {"LOW_CONFIDENCE_FACT", "MISSING_EVIDENCE", "POSSIBLE_DUPLICATE_ENTITY"} <= {item.reason_code for item in items}
```

Run: `.venv/bin/python -m pytest apps/api/tests/review/test_rules.py -v`

Expected: PASS.

- [ ] **Step 4: Update README**

Modify `README.md` with this section:

~~~md
### 阶段三：审核与质量改进

阶段三新增 `/review` 审核工作台。构建完成后，系统可扫描项目图谱生成待审核项；审核员可以接受/拒绝事实、合并重复实体、拆出别名，并通过审计日志追踪每次变更。

默认图谱和问答读取审核后有效数据。被拒绝事实不会出现在图谱和问答中，但原始证据和审计记录会保留。

常用命令：

```bash
curl -X POST http://127.0.0.1:8000/api/projects/xiaoao/review/scan
open http://127.0.0.1:5173/review
```
~~~

- [ ] **Step 5: Bump version to 0.3.0**

Run:

```bash
npm --prefix apps/web version 0.3.0 --no-git-tag-version
npm --prefix tests/e2e version 0.3.0 --no-git-tag-version
```

Modify `apps/api/pyproject.toml`:

```toml
version = "0.3.0"
```

- [ ] **Step 6: Run full verification**

Run:

```bash
SOURCE_PATH=/Users/yonglun/Repo/tspw-graph/笑傲江湖/笑傲江湖.txt make verify
```

Expected:

- Docker Compose build and health checks pass;
- backend tests pass;
- frontend Vitest tests pass;
- frontend typecheck passes;
- production build passes;
- evidence validation passes;
- Phase 1 E2E, online-build E2E and review E2E pass.

- [ ] **Step 7: Leak checks**

Run:

```bash
git grep -n -E 'sk-[A-Za-z0-9_-]{20,}|Bearer [A-Za-z0-9_-]{20,}' -- ':!docs/superpowers/plans/*' || true
git ls-files '笑傲江湖/**'
```

Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add README.md Makefile apps/api apps/web tests/e2e docs/superpowers/plans/2026-07-07-xiaoao-jianghu-phase-3-review-quality.md
git commit -m "test: verify review quality workflow end to end"
```

---

## Final Verification

Before declaring Phase 3 complete, run:

```bash
SOURCE_PATH=/Users/yonglun/Repo/tspw-graph/笑傲江湖/笑傲江湖.txt make verify
git status --short
rg -n -- "- \\[ \\]" docs/superpowers/plans/2026-07-07-xiaoao-jianghu-phase-3-review-quality.md || true
```

Expected:

- `make verify` exits 0;
- `git status --short` is clean after final commit;
- no unchecked boxes remain in this plan document once execution is complete.
