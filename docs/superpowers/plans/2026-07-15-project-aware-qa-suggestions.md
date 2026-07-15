# Project-Aware QA Suggestions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hard-coded《笑傲江湖》Ask-page label and 令狐冲 samples with evidence-backed suggestions generated from the currently selected project.

**Architecture:** A read-only Neo4j aggregation selects the richest eligible `Person` and reports answerable relation/property capabilities. A small QA suggestion service converts those capabilities into the existing controlled question templates, and `GET /api/projects/{project_id}/qa-suggestions` combines them with the SQLite project title. The React page is keyed by `projectId`, so switching projects synchronously remounts all local state while an abortable request loads the new suggestions.

**Tech Stack:** Python 3.12, FastAPI, Pydantic 2, Neo4j 5/Cypher, pytest, React 19, TypeScript 5.8, Vitest, Testing Library.

## Global Constraints

- Do not call an LLM to select an entity or generate suggestions.
- Return at most 6 suggestions, and only for capabilities already supported by the controlled QA parser and answer service.
- Count only non-merged `Person` entities, non-rejected facts, non-empty attributes, and records with at least one Evidence node.
- Scope every Neo4j match by the requested `project_id`; never mix projects.
- Keep the suggestions endpoint public and read-only; administrator authorization boundaries remain unchanged.
- On project switch, old input, answer, technical-detail state, errors, and suggestions must disappear without a browser refresh.
- A stale or aborted request must never overwrite the currently selected project.

## File Structure

- Create `apps/api/src/app/qa/suggestions.py`: controlled capability ordering, question copy, and response construction.
- Modify `apps/api/src/app/qa/models.py`: Pydantic contracts for representative entity and suggestions response.
- Modify `apps/api/src/app/graph/repository.py`: one bounded Neo4j aggregation that selects the representative `Person`.
- Modify `apps/api/src/app/projects/router.py`: public read-only suggestions endpoint that verifies the project and maps graph errors.
- Create `apps/api/tests/qa/test_suggestions.py`: pure suggestion-service ranking/output tests.
- Modify `apps/api/tests/graph/test_service.py`: repository query scope, eligibility, bounds, and record mapping tests.
- Modify `apps/api/tests/projects/test_router.py`: endpoint response, empty result, 404, and graph-unavailable tests.
- Modify `apps/api/tests/qa/test_live_api.py`: optional live-Neo4j proof that every returned suggestion is answerable with evidence.
- Modify `apps/web/src/api/client.ts`: TypeScript response contracts and abortable fetch helper.
- Modify `apps/web/src/features/ask/AskPage.tsx`: project-aware label, dynamic samples, empty/error states, and synchronous state reset.
- Modify `apps/web/src/features/ask/AskPage.test.tsx`: dynamic project, race, empty/error, and submission regression tests.

---

### Task 1: Controlled QA Suggestion Service

**Files:**
- Create: `apps/api/src/app/qa/suggestions.py`
- Modify: `apps/api/src/app/qa/models.py`
- Create: `apps/api/tests/qa/test_suggestions.py`

**Interfaces:**
- Consumes: `repository.qa_suggestion_candidate(project_id: str) -> dict[str, Any] | None` from Task 2.
- Produces: `QaSuggestionService.suggest(project_id: str, project_title: str) -> QaSuggestionsResponse`, `QaSuggestionsResponse`, `QaSuggestion`, and `QaRepresentativeEntity`.

- [ ] **Step 1: Write failing service tests for ordered, bounded, evidence-qualified capabilities**

Create `apps/api/tests/qa/test_suggestions.py` with a fake repository returning the already-aggregated candidate shape:

```python
from app.qa.suggestions import QaSuggestionService


class Repository:
    def __init__(self, candidate):
        self.candidate = candidate
        self.calls = []

    def qa_suggestion_candidate(self, project_id: str):
        self.calls.append(project_id)
        return self.candidate


def test_builds_ordered_questions_from_supported_capabilities() -> None:
    repository = Repository({
        "entity": {"id": "chen", "name": "陈家洛", "type": "Person"},
        "relation_capabilities": ["KNOWS", "MEMBER_OF", "MASTER_OF"],
        "property_capabilities": [
            "characteristic", "honorific", "identity", "gender"
        ],
    })

    response = QaSuggestionService(repository).suggest("project-book", "书剑恩仇录")

    assert response.project_id == "project-book"
    assert response.project_title == "书剑恩仇录"
    assert response.representative_entity is not None
    assert response.representative_entity.name == "陈家洛"
    assert [item.capability for item in response.suggestions] == [
        "MASTER_OF", "MEMBER_OF", "KNOWS", "gender", "identity", "honorific"
    ]
    assert response.suggestions[0].question == "陈家洛的师父是谁？"
    assert len(response.suggestions) == 6
    assert repository.calls == ["project-book"]


def test_returns_empty_response_without_answerable_candidate() -> None:
    response = QaSuggestionService(Repository(None)).suggest("empty", "空项目")

    assert response.project_title == "空项目"
    assert response.representative_entity is None
    assert response.suggestions == []


def test_ignores_unknown_capabilities() -> None:
    response = QaSuggestionService(Repository({
        "entity": {"id": "person", "name": "人物", "type": "Person"},
        "relation_capabilities": ["ALLY_OF"],
        "property_capabilities": ["birthday"],
    })).suggest("project", "小说")

    assert response.representative_entity is None
    assert response.suggestions == []
```

- [ ] **Step 2: Run the new test and verify the missing-module failure**

Run:

```bash
cd apps/api
pytest tests/qa/test_suggestions.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'app.qa.suggestions'`.

- [ ] **Step 3: Add the exact API models**

Append to `apps/api/src/app/qa/models.py`:

```python
from typing import Literal


class QaRepresentativeEntity(BaseModel):
    id: str
    name: str
    type: str


class QaSuggestion(BaseModel):
    id: str
    question: str
    kind: Literal["relation", "attribute"]
    capability: str


class QaSuggestionsResponse(BaseModel):
    project_id: str
    project_title: str
    representative_entity: QaRepresentativeEntity | None = None
    suggestions: list[QaSuggestion] = Field(default_factory=list)
```

Move `from typing import Literal` to the import section rather than leaving it between declarations.

- [ ] **Step 4: Implement the controlled suggestion builder**

Create `apps/api/src/app/qa/suggestions.py`:

```python
from typing import Any

from app.qa.models import (
    QaRepresentativeEntity,
    QaSuggestion,
    QaSuggestionsResponse,
)


RELATION_QUESTIONS = (
    ("MASTER_OF", "{name}的师父是谁？"),
    ("MEMBER_OF", "{name}属于哪个门派？"),
    ("KNOWS", "{name}掌握什么武功？"),
)

ATTRIBUTE_QUESTIONS = (
    ("gender", "{name}的性别是什么？"),
    ("identity", "{name}是什么身份？"),
    ("honorific", "{name}有哪些称号？"),
    ("life_status", "{name}是否在世？"),
    ("activity_region", "{name}的活动区域在哪里？"),
    ("region", "{name}的所在区域是哪里？"),
    ("characteristic", "{name}有什么特点？"),
)


class QaSuggestionService:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def suggest(self, project_id: str, project_title: str) -> QaSuggestionsResponse:
        candidate = self.repository.qa_suggestion_candidate(project_id)
        if candidate is None:
            return QaSuggestionsResponse(
                project_id=project_id,
                project_title=project_title,
            )

        entity = candidate.get("entity") or {}
        name = str(entity.get("name") or "").strip()
        relation_capabilities = set(candidate.get("relation_capabilities") or [])
        property_capabilities = set(candidate.get("property_capabilities") or [])
        suggestions = [
            QaSuggestion(
                id=f"relation:{capability}",
                question=template.format(name=name),
                kind="relation",
                capability=capability,
            )
            for capability, template in RELATION_QUESTIONS
            if capability in relation_capabilities
        ]
        suggestions.extend(
            QaSuggestion(
                id=f"attribute:{capability}",
                question=template.format(name=name),
                kind="attribute",
                capability=capability,
            )
            for capability, template in ATTRIBUTE_QUESTIONS
            if capability in property_capabilities
        )
        suggestions = suggestions[:6]
        if not name or not suggestions:
            return QaSuggestionsResponse(
                project_id=project_id,
                project_title=project_title,
            )
        return QaSuggestionsResponse(
            project_id=project_id,
            project_title=project_title,
            representative_entity=QaRepresentativeEntity.model_validate(entity),
            suggestions=suggestions,
        )
```

- [ ] **Step 5: Run the service tests**

Run:

```bash
cd apps/api
pytest tests/qa/test_suggestions.py -q
```

Expected: `3 passed`.

- [ ] **Step 6: Commit the service contract**

```bash
git add apps/api/src/app/qa/models.py apps/api/src/app/qa/suggestions.py apps/api/tests/qa/test_suggestions.py
git commit -m "feat: add controlled QA suggestion service"
```

---

### Task 2: Bounded Neo4j Representative-Person Query

**Files:**
- Modify: `apps/api/src/app/graph/repository.py`
- Modify: `apps/api/tests/graph/test_service.py`

**Interfaces:**
- Consumes: Neo4j nodes `Entity`, `Fact`, `AttributeAssertion`, and `Evidence` already written by the importer.
- Produces: `Neo4jGraphRepository.qa_suggestion_candidate(project_id: str) -> dict[str, Any] | None` with keys `entity`, `relation_capabilities`, and `property_capabilities`.

- [ ] **Step 1: Write failing repository mapping and query-safety tests**

Append to `apps/api/tests/graph/test_service.py`:

```python
def test_qa_suggestion_candidate_is_project_scoped_evidence_backed_and_bounded() -> None:
    record = {
        "entity": {
            "id": "chen",
            "project_id": "p-1",
            "type": "Person",
            "name": "陈家洛",
        },
        "relation_capabilities": ["MEMBER_OF", "KNOWS"],
        "property_capabilities": ["gender"],
    }
    session = FakeSession(record)
    repository = Neo4jGraphRepository(FakeDriver(session))

    result = repository.qa_suggestion_candidate("p-1")

    assert result == record
    assert session.parameters == {
        "project_id": "p-1",
        "supported_properties": [
            "gender", "identity", "honorific", "life_status",
            "activity_region", "region", "characteristic",
        ],
    }
    assert "person:Entity {project_id: $project_id, type: 'Person'}" in session.statement
    assert session.statement.count("EVIDENCED_BY") >= 4
    assert "coalesce(fact.review_status, 'ACCEPTED') <> 'REJECTED'" in session.statement
    assert "coalesce(person.review_status, 'ACCEPTED') <> 'MERGED'" in session.statement
    assert "ORDER BY relationship_count DESC" in session.statement
    assert "LIMIT 1" in session.statement


def test_qa_suggestion_candidate_returns_none_for_empty_project() -> None:
    repository = Neo4jGraphRepository(FakeDriver(FakeSession(None)))

    assert repository.qa_suggestion_candidate("empty") is None
```

- [ ] **Step 2: Run the repository tests and verify the missing-method failure**

Run:

```bash
cd apps/api
pytest tests/graph/test_service.py -q
```

Expected: the two new tests fail with `AttributeError: 'Neo4jGraphRepository' object has no attribute 'qa_suggestion_candidate'`.

- [ ] **Step 3: Implement one database-side ranking query**

Add this method to `Neo4jGraphRepository` in `apps/api/src/app/graph/repository.py`:

```python
    def qa_suggestion_candidate(self, project_id: str) -> dict[str, Any] | None:
        supported_properties = [
            "gender",
            "identity",
            "honorific",
            "life_status",
            "activity_region",
            "region",
            "characteristic",
        ]
        statement = """
            MATCH (person:Entity {project_id: $project_id, type: 'Person'})
            WHERE coalesce(person.review_status, 'ACCEPTED') <> 'MERGED'
            CALL {
                WITH person
                OPTIONAL MATCH (fact:Fact {project_id: $project_id})-[:TARGET]->(person)
                WHERE fact.type = 'MASTER_OF'
                  AND coalesce(fact.review_status, 'ACCEPTED') <> 'REJECTED'
                OPTIONAL MATCH (fact)-[:SOURCE]->(source:Entity {project_id: $project_id})
                OPTIONAL MATCH (fact)-[:EVIDENCED_BY]->(evidence:Evidence {project_id: $project_id})
                WHERE coalesce(source.review_status, 'ACCEPTED') <> 'MERGED'
                RETURN collect(DISTINCT CASE WHEN evidence IS NOT NULL THEN fact END) AS master_facts
            }
            CALL {
                WITH person
                OPTIONAL MATCH (fact:Fact {project_id: $project_id})-[:SOURCE]->(person)
                WHERE fact.type = 'MEMBER_OF'
                  AND coalesce(fact.review_status, 'ACCEPTED') <> 'REJECTED'
                OPTIONAL MATCH (fact)-[:TARGET]->(target:Entity {project_id: $project_id})
                OPTIONAL MATCH (fact)-[:EVIDENCED_BY]->(evidence:Evidence {project_id: $project_id})
                WHERE coalesce(target.review_status, 'ACCEPTED') <> 'MERGED'
                RETURN collect(DISTINCT CASE WHEN evidence IS NOT NULL THEN fact END) AS member_facts
            }
            CALL {
                WITH person
                OPTIONAL MATCH (fact:Fact {project_id: $project_id})-[:SOURCE]->(person)
                WHERE fact.type = 'KNOWS'
                  AND coalesce(fact.review_status, 'ACCEPTED') <> 'REJECTED'
                OPTIONAL MATCH (fact)-[:TARGET]->(target:Entity {project_id: $project_id})
                OPTIONAL MATCH (fact)-[:EVIDENCED_BY]->(evidence:Evidence {project_id: $project_id})
                WHERE coalesce(target.review_status, 'ACCEPTED') <> 'MERGED'
                RETURN collect(DISTINCT CASE WHEN evidence IS NOT NULL THEN fact END) AS knows_facts
            }
            CALL {
                WITH person
                OPTIONAL MATCH (person)-[:HAS_ATTRIBUTE]->(attribute:AttributeAssertion {project_id: $project_id})
                WHERE attribute.property_id IN $supported_properties
                  AND trim(toString(attribute.value)) <> ''
                OPTIONAL MATCH (attribute)-[:EVIDENCED_BY]->(evidence:Evidence {project_id: $project_id})
                WITH attribute, count(DISTINCT evidence) AS evidence_count
                WHERE attribute IS NOT NULL AND evidence_count > 0
                RETURN collect(DISTINCT attribute) AS attributes
            }
            WITH person, master_facts, member_facts, knows_facts, attributes,
                size(master_facts) + size(member_facts) + size(knows_facts) AS relationship_count,
                size(attributes) AS attribute_count
            WITH person, relationship_count, attribute_count,
                [capability IN [
                    CASE WHEN size(master_facts) > 0 THEN 'MASTER_OF' END,
                    CASE WHEN size(member_facts) > 0 THEN 'MEMBER_OF' END,
                    CASE WHEN size(knows_facts) > 0 THEN 'KNOWS' END
                ] WHERE capability IS NOT NULL] AS relation_capabilities,
                [property_id IN $supported_properties
                    WHERE any(attribute IN attributes
                        WHERE attribute.property_id = property_id)] AS property_capabilities
            WHERE relationship_count > 0 OR attribute_count > 0
            RETURN properties(person) AS entity,
                relation_capabilities,
                property_capabilities
            ORDER BY relationship_count DESC,
                attribute_count DESC,
                size(relation_capabilities) + size(property_capabilities) DESC,
                person.name,
                person.id
            LIMIT 1
        """
        with self.driver.session() as session:
            record = session.run(
                statement,
                project_id=project_id,
                supported_properties=supported_properties,
            ).single()
            if record is None:
                return None
            return {
                "entity": record["entity"],
                "relation_capabilities": record["relation_capabilities"],
                "property_capabilities": record["property_capabilities"],
            }
```

- [ ] **Step 4: Run the graph repository tests**

Run:

```bash
cd apps/api
pytest tests/graph/test_service.py -q
```

Expected: all tests in the file pass, including the two new candidate-query tests.

- [ ] **Step 5: Commit the bounded graph query**

```bash
git add apps/api/src/app/graph/repository.py apps/api/tests/graph/test_service.py
git commit -m "feat: select evidence-backed QA representative"
```

---

### Task 3: Public Project Suggestions Endpoint

**Files:**
- Modify: `apps/api/src/app/projects/router.py`
- Modify: `apps/api/tests/projects/test_router.py`
- Modify: `apps/api/tests/qa/test_live_api.py`

**Interfaces:**
- Consumes: `QaSuggestionService.suggest(project_id, project.title)` from Task 1 and `get_repository`/`execute` from the existing graph router.
- Produces: `GET /api/projects/{project_id}/qa-suggestions -> QaSuggestionsResponse`.

- [ ] **Step 1: Extend the project-router fixture with a fake suggestions repository**

In `apps/api/tests/projects/test_router.py`, import `ServiceUnavailable` and `get_repository`, then add:

```python
from neo4j.exceptions import ServiceUnavailable

from app.graph.router import get_repository


class FakeSuggestionRepository:
    def __init__(self, candidate=None, error: Exception | None = None) -> None:
        self.candidate = candidate
        self.error = error

    def qa_suggestion_candidate(self, project_id: str):
        if self.error is not None:
            raise self.error
        return self.candidate
```

Replace `make_client` with this version, which accepts a suggestion repository and overrides `get_repository`:

```python
def make_client(tmp_path, suggestions=None) -> tuple[TestClient, ProjectRepository]:
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
    suggestion_repository = (
        suggestions if suggestions is not None else FakeSuggestionRepository()
    )
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_ready_admin] = lambda: AdminAccount(
        id="admin-test",
        username="admin",
        normalized_username="admin",
        password_hash="hash",
    )
    app.dependency_overrides[get_project_service] = lambda: service
    app.dependency_overrides[get_upload_service] = lambda: ProjectUploadService(
        repository, uploads
    )
    app.dependency_overrides[get_job_repository] = lambda: JobRepository(
        repository.engine
    )
    app.dependency_overrides[get_repository] = lambda: suggestion_repository
    return TestClient(app), repository
```

- [ ] **Step 2: Write failing endpoint tests**

Append:

```python
def test_project_qa_suggestions_use_project_title_and_graph_candidate(tmp_path):
    graph = FakeSuggestionRepository({
        "entity": {"id": "chen", "name": "陈家洛", "type": "Person"},
        "relation_capabilities": ["MEMBER_OF"],
        "property_capabilities": ["gender"],
    })
    client, repository = make_client(tmp_path, graph)
    project = next(item for item in repository.list_projects() if not item.is_builtin)

    response = client.get(f"/api/projects/{project.id}/qa-suggestions")

    assert response.status_code == 200
    assert response.json()["project_title"] == "测试小说"
    assert [item["question"] for item in response.json()["suggestions"]] == [
        "陈家洛属于哪个门派？", "陈家洛的性别是什么？"
    ]


def test_project_qa_suggestions_return_empty_for_empty_graph(tmp_path):
    client, repository = make_client(tmp_path)
    project = next(item for item in repository.list_projects() if not item.is_builtin)

    response = client.get(f"/api/projects/{project.id}/qa-suggestions")

    assert response.status_code == 200
    assert response.json()["representative_entity"] is None
    assert response.json()["suggestions"] == []


def test_project_qa_suggestions_report_missing_project(tmp_path):
    client, _ = make_client(tmp_path)

    response = client.get("/api/projects/missing/qa-suggestions")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "PROJECT_NOT_FOUND"


def test_project_qa_suggestions_map_graph_outage_to_503(tmp_path):
    graph = FakeSuggestionRepository(error=ServiceUnavailable("offline"))
    client, repository = make_client(tmp_path, graph)
    project = next(item for item in repository.list_projects() if not item.is_builtin)

    response = client.get(f"/api/projects/{project.id}/qa-suggestions")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "GRAPH_UNAVAILABLE"
```

- [ ] **Step 3: Run the endpoint tests and verify 404 failures for the new route**

Run:

```bash
cd apps/api
pytest tests/projects/test_router.py -q
```

Expected: the four new tests fail because `/qa-suggestions` is not registered.

- [ ] **Step 4: Add the endpoint before the generic project GET route**

In `apps/api/src/app/projects/router.py`, import:

```python
from app.graph.router import Repository, execute
from app.qa.models import QaSuggestionsResponse
from app.qa.suggestions import QaSuggestionService
```

Then add this route immediately before `@router.get("/{project_id}")`:

```python
@router.get(
    "/{project_id}/qa-suggestions",
    response_model=QaSuggestionsResponse,
)
def project_qa_suggestions(
    project_id: str,
    service: Service,
    repository: Repository,
) -> QaSuggestionsResponse:
    try:
        project = service.get(project_id)
    except ProjectNotFoundError as error:
        raise HTTPException(
            status_code=404,
            detail={"code": "PROJECT_NOT_FOUND"},
        ) from error
    return execute(
        lambda: QaSuggestionService(repository).suggest(project.id, project.title)
    )
```

Do not add `require_ready_admin`; this is the read-only public endpoint specified in the design.

- [ ] **Step 5: Run endpoint and QA suites**

Append this integration check to `apps/api/tests/qa/test_live_api.py`; it remains guarded by the file's existing `RUN_NEO4J_INTEGRATION=1` marker:

```python
def test_live_suggestions_are_answerable_with_evidence(client: TestClient) -> None:
    response = client.get("/api/projects/xiaoao/qa-suggestions")

    assert response.status_code == 200
    body = response.json()
    assert body["project_title"] == "笑傲江湖"
    assert body["representative_entity"]["type"] == "Person"
    assert 1 <= len(body["suggestions"]) <= 6

    for suggestion in body["suggestions"]:
        answer = client.post(
            "/api/ask",
            json={
                "project_id": "xiaoao",
                "question": suggestion["question"],
            },
        )
        assert answer.status_code == 200
        assert answer.json()["answer"] != "图谱中暂无足够事实"
        assert answer.json()["evidence"]
```

Run the fast endpoint and QA suites:

```bash
cd apps/api
pytest tests/projects/test_router.py tests/qa -q
```

Expected: all selected tests pass; live tests are skipped unless `RUN_NEO4J_INTEGRATION=1` is explicitly enabled. When Neo4j is available, also run `RUN_NEO4J_INTEGRATION=1 pytest tests/qa/test_live_api.py -q` and expect all live QA tests to pass.

- [ ] **Step 6: Commit the endpoint**

```bash
git add apps/api/src/app/projects/router.py apps/api/tests/projects/test_router.py apps/api/tests/qa/test_live_api.py
git commit -m "feat: expose project QA suggestions"
```

---

### Task 4: Project-Aware Ask Page With Race-Safe Reset

**Files:**
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/features/ask/AskPage.tsx`
- Modify: `apps/web/src/features/ask/AskPage.test.tsx`

**Interfaces:**
- Consumes: `GET /api/projects/{project_id}/qa-suggestions` from Task 3 and the existing `ProjectContext` (`projects`, `projectId`).
- Produces: `getQaSuggestions(projectId: string, signal?: AbortSignal): Promise<QaSuggestionsResponse>` and a remount-on-project-change Ask UI.

- [ ] **Step 1: Replace hard-coded-sample tests with dynamic-project tests**

Rewrite `apps/web/src/features/ask/AskPage.test.tsx` around a reusable fetch mock. The key assertions must include:

```tsx
const projects = [
  { id: 'project-xiaoao', title: '笑傲江湖', is_builtin: false, created_at: '', updated_at: '' },
  { id: 'project-shujian', title: '书剑恩仇录', is_builtin: false, created_at: '', updated_at: '' },
]

const suggestions = {
  project_id: 'project-shujian',
  project_title: '书剑恩仇录',
  representative_entity: { id: 'chen', name: '陈家洛', type: 'Person' },
  suggestions: [
    { id: 'relation:MEMBER_OF', question: '陈家洛属于哪个门派？', kind: 'relation', capability: 'MEMBER_OF' },
    { id: 'attribute:gender', question: '陈家洛的性别是什么？', kind: 'attribute', capability: 'gender' },
  ],
}

it('uses the selected project title and dynamic suggestions', async () => {
  vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
    const url = String(input)
    if (url === '/api/projects') return new Response(JSON.stringify(projects))
    if (url.includes('/api/projects/project-shujian/qa-suggestions')) {
      return new Response(JSON.stringify(suggestions))
    }
    return new Response(JSON.stringify({ ...suggestions, project_id: 'project-xiaoao', project_title: '笑傲江湖' }))
  }))

  render(
    <MemoryRouter initialEntries={['/ask?project=project-shujian']}>
      <ProjectProvider><AskPage /></ProjectProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByText('向《书剑恩仇录》图谱提问')).toBeVisible()
  expect(screen.getByRole('button', { name: '陈家洛属于哪个门派？' })).toBeVisible()
  expect(screen.queryByText(/令狐冲/)).not.toBeInTheDocument()
})
```

Add these three tests with explicit fetch behavior and assertions (also import `act`, `waitFor`, and `ProjectSwitcher`):

```tsx
it('shows an empty recommendation state without hard-coded fallbacks', async () => {
  vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request) => {
    const url = String(input)
    if (url === '/api/projects') return new Response(JSON.stringify(projects))
    return new Response(JSON.stringify({
      project_id: 'project-shujian',
      project_title: '书剑恩仇录',
      representative_entity: null,
      suggestions: [],
    }))
  }))

  render(
    <MemoryRouter initialEntries={['/ask?project=project-shujian']}>
      <ProjectProvider><AskPage /></ProjectProvider>
    </MemoryRouter>,
  )

  expect(await screen.findByText('当前项目暂无可推荐的问题')).toBeVisible()
  expect(screen.queryByText(/令狐冲/)).not.toBeInTheDocument()
})

it('clears the previous answer when the project changes', async () => {
  const fetchMock = vi.fn(async (input: string | URL | Request) => {
    const url = String(input)
    if (url === '/api/projects') return new Response(JSON.stringify(projects))
    if (url.includes('project-shujian/qa-suggestions')) {
      return new Response(JSON.stringify(suggestions))
    }
    if (url.includes('project-xiaoao/qa-suggestions')) {
      return new Response(JSON.stringify({
        project_id: 'project-xiaoao',
        project_title: '笑傲江湖',
        representative_entity: { id: 'linghu', name: '令狐冲', type: 'Person' },
        suggestions: [{
          id: 'attribute:gender', question: '令狐冲的性别是什么？',
          kind: 'attribute', capability: 'gender',
        }],
      }))
    }
    if (url === '/api/ask') return new Response(JSON.stringify(response))
    throw new Error(`unexpected request: ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  const user = userEvent.setup()

  render(
    <MemoryRouter initialEntries={['/ask?project=project-xiaoao']}>
      <ProjectProvider><ProjectSwitcher /><AskPage /></ProjectProvider>
    </MemoryRouter>,
  )

  await user.click(await screen.findByRole('button', { name: '令狐冲的性别是什么？' }))
  await user.click(screen.getByRole('button', { name: '查询图谱' }))
  expect(await screen.findByRole('heading', { name: '令狐沖的性别是男。' })).toBeVisible()

  await user.selectOptions(screen.getByRole('combobox', { name: '当前项目' }), 'project-shujian')

  expect(screen.queryByRole('heading', { name: '令狐沖的性别是男。' })).not.toBeInTheDocument()
  expect(await screen.findByText('向《书剑恩仇录》图谱提问')).toBeVisible()
  expect(await screen.findByRole('button', { name: '陈家洛属于哪个门派？' })).toBeVisible()
})

it('ignores an older suggestions response after a rapid project switch', async () => {
  let resolveOld!: (response: Response) => void
  const oldRequest = new Promise<Response>(resolve => { resolveOld = resolve })
  vi.stubGlobal('fetch', vi.fn((input: string | URL | Request) => {
    const url = String(input)
    if (url === '/api/projects') return Promise.resolve(new Response(JSON.stringify(projects)))
    if (url.includes('project-xiaoao/qa-suggestions')) return oldRequest
    if (url.includes('project-shujian/qa-suggestions')) {
      return Promise.resolve(new Response(JSON.stringify(suggestions)))
    }
    return Promise.reject(new Error(`unexpected request: ${url}`))
  }))
  const user = userEvent.setup()

  render(
    <MemoryRouter initialEntries={['/ask?project=project-xiaoao']}>
      <ProjectProvider><ProjectSwitcher /><AskPage /></ProjectProvider>
    </MemoryRouter>,
  )

  await user.selectOptions(await screen.findByRole('combobox', { name: '当前项目' }), 'project-shujian')
  expect(await screen.findByRole('button', { name: '陈家洛属于哪个门派？' })).toBeVisible()

  await act(async () => {
    resolveOld(new Response(JSON.stringify({
      project_id: 'project-xiaoao',
      project_title: '笑傲江湖',
      representative_entity: { id: 'linghu', name: '令狐冲', type: 'Person' },
      suggestions: [{
        id: 'relation:MASTER_OF', question: '令狐冲的师父是谁？',
        kind: 'relation', capability: 'MASTER_OF',
      }],
    })))
  })

  await waitFor(() => expect(screen.queryByText('令狐冲的师父是谁？')).not.toBeInTheDocument())
  expect(screen.getByText('向《书剑恩仇录》图谱提问')).toBeVisible()
})
```

Add the submission regression using the dynamic suggestion:

```tsx
it('submits a dynamic attribute question and renders evidence', async () => {
  const fetchMock = vi.fn(async (input: string | URL | Request) => {
    const url = String(input)
    if (url === '/api/projects') return new Response(JSON.stringify(projects))
    if (url.includes('project-shujian/qa-suggestions')) {
      return new Response(JSON.stringify(suggestions))
    }
    if (url === '/api/ask') return new Response(JSON.stringify(response))
    throw new Error(`unexpected request: ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  const user = userEvent.setup()
  render(
    <MemoryRouter initialEntries={['/ask?project=project-shujian']}>
      <ProjectProvider><AskPage /></ProjectProvider>
    </MemoryRouter>,
  )

  await user.click(await screen.findByRole('button', { name: '陈家洛的性别是什么？' }))
  await user.click(screen.getByRole('button', { name: '查询图谱' }))

  expect(await screen.findByRole('heading', { name: '令狐沖的性别是男。' })).toBeVisible()
  expect(screen.getByText('令狐冲是男')).toBeVisible()
  expect(fetchMock).toHaveBeenCalledWith('/api/ask', expect.objectContaining({ method: 'POST' }))
})
```

- [ ] **Step 2: Run Ask-page tests and verify failures against the hard-coded UI**

Run:

```bash
cd apps/web
npm test -- --run src/features/ask/AskPage.test.tsx
```

Expected: tests fail because the label and sample questions are still hard-coded and no suggestions request is made.

- [ ] **Step 3: Add TypeScript contracts and the abortable client helper**

Add to `apps/web/src/api/client.ts`:

```typescript
export type QaSuggestion = {
  id: string
  question: string
  kind: 'relation' | 'attribute'
  capability: string
}

export type QaSuggestionsResponse = {
  project_id: string
  project_title: string
  representative_entity: { id: string; name: string; type: string } | null
  suggestions: QaSuggestion[]
}

export function getQaSuggestions(projectId: string, signal?: AbortSignal) {
  return apiFetch<QaSuggestionsResponse>(
    `/api/projects/${encodeURIComponent(projectId)}/qa-suggestions`,
    { signal },
  )
}
```

- [ ] **Step 4: Refactor AskPage into a project-keyed wrapper and abortable body**

In `apps/web/src/features/ask/AskPage.tsx`, remove the `samples` constant. Keep the answer rendering markup, but structure state ownership as follows:

```tsx
import { FormEvent, useEffect, useState } from 'react'

import {
  apiFetch,
  getQaSuggestions,
  type AskResponse,
  type QaSuggestion,
} from '../../api/client'

export function AskPage() {
  const { projectId, projects } = useProject()
  const projectTitle = projects.find(project => project.id === projectId)?.title ?? '当前项目'
  return <AskProjectPage key={projectId} projectId={projectId} projectTitle={projectTitle} />
}

function AskProjectPage({ projectId, projectTitle }: { projectId: string; projectTitle: string }) {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<AskResponse>()
  const [loading, setLoading] = useState(false)
  const [details, setDetails] = useState(false)
  const [suggestions, setSuggestions] = useState<QaSuggestion[]>([])
  const [suggestionsLoading, setSuggestionsLoading] = useState(true)
  const [suggestionsError, setSuggestionsError] = useState(false)
  const [serverProjectTitle, setServerProjectTitle] = useState('')
  const displayProjectTitle = projectTitle === '当前项目'
    ? serverProjectTitle || projectTitle
    : projectTitle

  useEffect(() => {
    const controller = new AbortController()
    setSuggestionsLoading(true)
    setSuggestionsError(false)
    getQaSuggestions(projectId, controller.signal)
      .then(body => {
        if (body.project_id !== projectId) return
        setServerProjectTitle(body.project_title)
        setSuggestions(body.suggestions)
      })
      .catch(error => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setSuggestionsError(true)
      })
      .finally(() => {
        if (!controller.signal.aborted) setSuggestionsLoading(false)
      })
    return () => controller.abort()
  }, [projectId])

  const ask = async (event?: FormEvent) => {
    event?.preventDefault()
    if (!question.trim()) return
    setLoading(true)
    setDetails(false)
    try {
      setAnswer(await apiFetch<AskResponse>('/api/ask', {
        method: 'POST',
        body: JSON.stringify({ project_id: projectId, question }),
      }))
    } finally {
      setLoading(false)
    }
  }

  return <section className="page ask-page">
    <header className="page-header">
      <div>
        <p className="eyebrow">EXPLAINABLE QA · 05</p>
        <h1>答案不是猜出来的</h1>
        <p>每个回答同时展示图路径与原文证据；查不到时，系统明确拒答。</p>
      </div>
    </header>
    <div className="ask-layout">
      <div>
        <form onSubmit={ask} className="ask-form">
          <label htmlFor="question">向《{displayProjectTitle}》图谱提问</label>
          <div>
            <input id="question" value={question} onChange={event => setQuestion(event.target.value)} />
            <button className="primary" disabled={loading || !question.trim()}>
              {loading ? '查询中…' : '查询图谱'}
            </button>
          </div>
        </form>
        <div className="sample-questions" aria-live="polite">
          {suggestionsLoading && <p>正在生成当前项目的问题建议…</p>}
          {!suggestionsLoading && suggestionsError && <p>问题建议暂时不可用，仍可手动提问</p>}
          {!suggestionsLoading && !suggestionsError && suggestions.length === 0 && <p>当前项目暂无可推荐的问题</p>}
          {suggestions.map(item => (
            <button type="button" key={item.id} onClick={() => setQuestion(item.question)}>
              {item.question}
            </button>
          ))}
        </div>
      </div>
      {answer ? <article className="answer-card" aria-live="polite">
        <StatusDot tone={answer.evidence.length > 0 ? 'success' : 'warning'}>
          {answer.evidence.length > 0 ? '已找到可验证答案' : '答案缺少原文证据'}
        </StatusDot>
        <h2>{answer.answer}</h2>
        {answer.path.map((step, index) => <div className="answer-path" key={index}>
          <span>{step.source_name}</span><b>— {step.relation} →</b><span>{step.target_name}</span>
        </div>)}
        {answer.evidence.map(item => <blockquote key={item.id}>
          <small>第 {item.chapter_number} 章 · {item.chapter_title}</small>
          <p>{item.quote}</p>
        </blockquote>)}
        <button className="text-button" onClick={() => setDetails(!details)}>
          查看技术细节 {details ? '↑' : '↓'}
        </button>
        {details && <div className="tech-details">
          <p>{answer.query_explanation}</p>
          <pre>{answer.cypher_template || '未执行查询模板'}</pre>
          <code>{JSON.stringify(answer.parameters)}</code>
        </div>}
      </article> : <div className="answer-empty">
        <p>选择一个示例问题，观察答案如何由图事实和原文证据共同产生。</p>
      </div>}
    </div>
  </section>
}
```

Using `key={projectId}` is mandatory: it synchronously discards the previous project's input, answer, details, errors, and request lifecycle before the next paint, instead of relying only on a post-render effect reset.

- [ ] **Step 5: Run Ask-page tests and TypeScript checks**

Run:

```bash
cd apps/web
npm test -- --run src/features/ask/AskPage.test.tsx
npm run typecheck
```

Expected: all Ask-page tests pass and TypeScript exits with code 0.

- [ ] **Step 6: Run the complete regression gate**

Run:

```bash
cd apps/api
pytest tests/qa tests/projects/test_router.py tests/graph/test_service.py -q
cd ../web
npm test -- --run
npm run build
```

Expected: all selected backend tests, all frontend tests, and the production build pass. If the repository-wide backend suite is also run, record the already-known sandbox-only Neo4j failure separately rather than hiding it.

- [ ] **Step 7: Commit the frontend behavior**

```bash
git add apps/web/src/api/client.ts apps/web/src/features/ask/AskPage.tsx apps/web/src/features/ask/AskPage.test.tsx
git commit -m "fix: make Ask page project aware"
```

---

## Final Review Gate

- [ ] Run `git diff --check origin/master...HEAD` and confirm no whitespace errors.
- [ ] Run `rg -n "向《笑傲江湖》|const samples|令狐冲的师父" apps/web/src/features/ask` and confirm production code has no hard-coded project/sample copy.
- [ ] Confirm `GET /api/projects/{project_id}/qa-suggestions` is unauthenticated and read-only.
- [ ] Confirm every returned suggestion can be parsed by `parse_local_intent` and answered from at least one evidence-backed fact or attribute.
- [ ] Confirm the worktree is clean after all commits.
