# Entity Attributes and Graph Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add evidence-backed, ontology-defined entity attributes, expose them in entity details, support attribute-only backfill for existing projects, and render a one-hop graph within one second for common entities.

**Architecture:** Extend the ontology catalog with inheritable property definitions, normalize model output into first-class `AttributeAssertion` records, and import those records into Neo4j with evidence edges. Keep relations separate from attributes. Split graph and detail loading in the React client, optimize one-hop Cypher and Neo4j connection reuse, and offer two-hop expansion only on demand.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic 2, SQLAlchemy 2, Neo4j 5.26 Community / Neo4j Python driver 5.x, React 19, TypeScript 5.8, Cytoscape 3.33, Vitest 3.

## Global Constraints

- Preserve existing projects, entities, facts, evidence, review decisions, entity merges, SQLite data, and Docker volumes.
- Keep existing REST paths and existing response fields backward compatible; new fields must be additive and have safe defaults.
- Every extracted attribute value must cite an exact source quote shorter than or equal to 500 characters.
- Entity-to-entity semantics such as master, spouse, membership, knowledge, participation, and possession remain relations, not duplicated attributes.
- Attribute backfill is read-only from the user's perspective and writes only attribute assertions plus their evidence links.
- The graph defaults to one hop and at most 50 nodes; two-hop expansion is user initiated and capped at 100 nodes.
- Performance budgets on the Azure deployment: exact search API P95 <= 300 ms, one-hop API P95 <= 700 ms, layout <= 100 ms for 50 nodes, and click-to-visible one-hop graph <= 1 second.
- Do not add a frontend or backend dependency unless an existing standard-library or installed-library solution cannot satisfy the requirement.
- Implement each task test-first and leave the repository buildable after every commit.

---

## File Structure

### New files

- `apps/api/src/app/ontology/properties.py` — property lookup and inheritance resolution.
- `apps/api/tests/extraction/test_attribute_pipeline.py` — end-to-end attribute normalization and import tests.
- `apps/api/tests/jobs/test_attribute_jobs.py` — job-kind migration and attribute-job API tests.
- `apps/web/src/features/build/AttributeBackfill.tsx` — existing-project attribute backfill form.
- `scripts/check-graph-performance.py` — deployment timing check using the HTTP API.

### Existing files with focused changes

- `apps/api/src/app/ontology/models.py`, `catalog.py` — property definitions in the ontology contract.
- `apps/api/src/app/extraction/models.py`, `prompting.py`, `normalize.py`, `pipeline.py` — model output and normalization of attribute assertions.
- `apps/api/src/app/graph/models.py`, `importer.py`, `neo4j.py` — attribute domain records and persistence.
- `apps/api/src/app/jobs/models.py`, `repository.py`, `router.py` — job kind, schema upgrade, and response contract.
- `apps/api/src/app/projects/router.py` — create attribute backfill jobs.
- `apps/api/src/app/worker/online.py` — route full build and attribute-only backfill.
- `apps/api/src/app/main.py`, `graph/router.py`, `graph/repository.py`, `graph/service.py` — shared Driver, indexed search, optimized one-hop query, and enriched detail.
- `apps/web/src/api/client.ts` — additive API types and abort-aware requests.
- `apps/web/src/features/graph/GraphPage.tsx`, `GraphCanvas.tsx`, `EntityPanel.tsx` — staged loading, fast layout, two-hop action, attributes, relations, and evidence.
- `apps/web/src/features/build/BuildPage.tsx`, `QualityReport.tsx` — backfill entry and attribute quality metrics.
- `docs/deployment-docker-azure-openai.md` — backfill and performance-check operations.

---

### Task 1: Define Inheritable Ontology Properties

**Files:**
- Create: `apps/api/src/app/ontology/properties.py`
- Modify: `apps/api/src/app/ontology/models.py`
- Modify: `apps/api/src/app/ontology/catalog.py`
- Test: `apps/api/tests/ontology/test_catalog.py`

**Interfaces:**
- Produces: `PropertyValueType`, `PropertyDefinition`, `EntityTypeDefinition.property_definitions`, `property_definitions_for(entity_type: EntityType) -> tuple[PropertyDefinition, ...]`, and `property_definition_for(entity_type: EntityType, property_id: str) -> PropertyDefinition | None`.
- Consumed by: Tasks 2, 3, 8, and 10.

- [ ] **Step 1: Write failing ontology property tests**

Add tests proving direct properties, inheritance, and duplicate-property override rules:

```python
from app.ontology.models import EntityType
from app.ontology.properties import property_definition_for, property_definitions_for


def test_person_exposes_typed_property_definitions(client):
    body = client.get("/api/ontology").json()
    person = next(item for item in body["entity_types"] if item["id"] == "Person")
    assert {item["id"] for item in person["effective_property_definitions"]} >= {
        "gender", "honorific", "identity", "life_status"
    }
    honorific = next(item for item in person["effective_property_definitions"] if item["id"] == "honorific")
    assert honorific["value_type"] == "TEXT"
    assert honorific["multiple"] is True


def test_swordplay_inherits_martial_art_properties():
    ids = {item.id for item in property_definitions_for(EntityType.SWORDPLAY)}
    assert {"weapon_type", "characteristic", "prerequisite", "effect"} <= ids
    assert property_definition_for(EntityType.SWORDPLAY, "effect") is not None
```

- [ ] **Step 2: Run the tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/ontology/test_catalog.py -q
```

Expected: collection or assertion failure because property models and resolver do not exist.

- [ ] **Step 3: Add property contracts and catalog definitions**

Implement these contracts in `ontology/models.py`:

```python
class PropertyValueType(StrEnum):
    TEXT = "TEXT"
    NUMBER = "NUMBER"
    BOOLEAN = "BOOLEAN"
    ENUM = "ENUM"


class PropertyDefinition(FrozenModel):
    id: str
    label: str
    description: str
    value_type: PropertyValueType = PropertyValueType.TEXT
    multiple: bool = False
    enum_values: tuple[str, ...] = ()


class EntityTypeDefinition(FrozenModel):
    id: EntityType
    label: str
    description: str
    color: str
    parent: EntityType | None = None
    property_definitions: tuple[PropertyDefinition, ...] = ()
    effective_property_definitions: tuple[PropertyDefinition, ...] = ()
```

Define the exact property set from the design in `catalog.py`. In `properties.py`, walk parent definitions from root to leaf, then merge by property ID while preserving first appearance order. Build `CATALOG` with resolved effective definitions after the direct catalog is declared.

Use these exact value contracts: `gender` is `ENUM("男", "女")`; `life_status` is `ENUM("在世", "死亡")`; `honorific`, `identity`, organization `characteristic`, `activity_region`, martial-art `characteristic`, `prerequisite`, `effect`, event `outcome`, and artifact `characteristic` are multi-value `TEXT`; all remaining properties are single-value `TEXT`. Omit uncertain values instead of emitting an “unknown” enum member.

- [ ] **Step 4: Run ontology tests**

Run the Task 1 pytest command again. Expected: all ontology tests pass.

- [ ] **Step 5: Commit the ontology contract**

```bash
git add apps/api/src/app/ontology apps/api/tests/ontology/test_catalog.py
git commit -m "feat: define evidence-backed ontology properties"
```

---

### Task 2: Extend the Model Extraction Contract with Attributes

**Files:**
- Modify: `apps/api/src/app/extraction/models.py`
- Modify: `apps/api/src/app/extraction/prompting.py`
- Modify: `apps/api/src/app/extraction/fixed.py`
- Test: `apps/api/tests/extraction/test_models.py`
- Test: `apps/api/tests/extraction/test_prompting.py`
- Test: `apps/api/tests/extraction/test_provider_contracts.py`

**Interfaces:**
- Consumes: `property_definitions_for` from Task 1.
- Produces: `CandidateAttribute`, `ExtractionResult.attributes`, and a strict structured-output schema requiring `entities`, `facts`, and `attributes`.
- Consumed by: Task 3.

- [ ] **Step 1: Write failing structured-output tests**

Add a valid attribute candidate and assert the strict JSON schema remains Azure-compatible:

```python
from app.extraction.models import ExtractionResult, strict_extraction_schema


def test_extraction_result_accepts_evidence_backed_attribute():
    result = ExtractionResult.model_validate({
        "entities": [{"local_id": "p1", "name": "令狐冲", "type": "Person", "aliases": []}],
        "facts": [],
        "attributes": [{
            "entity_local_id": "p1",
            "property_id": "identity",
            "value": "华山派大弟子",
            "evidence": {"start": 0, "end": 6, "quote": "华山派大弟子"},
            "confidence": 0.96,
        }],
    })
    assert result.attributes[0].property_id == "identity"


def test_strict_schema_requires_attributes_at_root():
    schema = strict_extraction_schema()
    assert schema["required"] == ["entities", "facts", "attributes"]
    assert schema["properties"]["attributes"]["items"]["additionalProperties"] is False
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/extraction/test_models.py apps/api/tests/extraction/test_prompting.py apps/api/tests/extraction/test_provider_contracts.py -q
```

Expected: failures for missing `CandidateAttribute` and `attributes` schema.

- [ ] **Step 3: Implement candidate models and strict schema**

Add:

```python
class CandidateAttribute(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_local_id: str = Field(max_length=100)
    property_id: str = Field(max_length=100)
    value: str = Field(max_length=500)
    evidence: CandidateEvidence
    confidence: float = Field(default=1.0, ge=0, le=1)


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entities: list[CandidateEntity] = Field(default_factory=list, max_length=100)
    facts: list[CandidateFact] = Field(default_factory=list, max_length=200)
    attributes: list[CandidateAttribute] = Field(default_factory=list, max_length=200)
```

Add the equivalent strict JSON schema. Extend `validate_for_chunk()` to validate fact and attribute evidence with the same exact-quote rule. Make `FixedProvider` return an empty attributes list unless its fixture contains a supported property phrase.

- [ ] **Step 4: Add property instructions to the system prompt**

Render effective properties per allowed entity type using this format:

```text
- Person.identity（身份，TEXT，可多值）：人物在文本中被明确说明的身份或地位。
```

Add explicit rules: only use allowed property IDs, never express another entity as an attribute value when a relation exists, omit uncertain values, and select the shortest exact quote.

- [ ] **Step 5: Run extraction contract tests**

Run the Task 2 pytest command again. Expected: all selected tests pass.

- [ ] **Step 6: Commit the extraction contract**

```bash
git add apps/api/src/app/extraction apps/api/tests/extraction
git commit -m "feat: extend extraction contract with attributes"
```

---

### Task 3: Normalize Attribute Values and Evidence

**Files:**
- Modify: `apps/api/src/app/graph/models.py`
- Modify: `apps/api/src/app/extraction/normalize.py`
- Modify: `apps/api/src/app/extraction/pipeline.py`
- Create: `apps/api/tests/extraction/test_attribute_pipeline.py`
- Modify: `apps/api/tests/extraction/test_normalize.py`
- Modify: `apps/api/tests/extraction/test_pipeline.py`

**Interfaces:**
- Consumes: `CandidateAttribute` and ontology property resolver.
- Produces: `AttributeAssertionRecord`, `NormalizedChunk.attributes`, `GraphDocument.attributes`, `QualityReport.accepted_attributes`, `QualityReport.accepted_attribute_evidence`, and `ImportSummary.created_attributes`.
- Consumed by: Tasks 4, 6, 8, and 10.

- [ ] **Step 1: Write failing normalization tests**

Cover a successful attribute and granular rejection cases:

```python
def test_normalizer_creates_stable_evidence_backed_attribute():
    chunk = TextChunk("c1", 1, 100, 106, "华山派大弟子")
    result = ExtractionResult.model_validate({
        "entities": [{"local_id": "p1", "name": "令狐冲", "type": "Person", "aliases": []}],
        "facts": [],
        "attributes": [{
            "entity_local_id": "p1", "property_id": "identity", "value": "华山派大弟子",
            "evidence": {"start": 0, "end": 6, "quote": "华山派大弟子"}, "confidence": 0.96,
        }],
    })
    normalized = normalize_chunk_result("p-1", chunk, result)
    assert normalized.attributes[0].entity_id == normalized.entities[0].id
    assert normalized.attributes[0].evidence_ids == [normalized.evidence[0].id]
    assert normalized.evidence[0].start_offset == 100


def test_invalid_attribute_is_rejected_without_dropping_entity():
    chunk = TextChunk("c1", 1, 0, 3, "令狐冲")
    result = ExtractionResult.model_validate({
        "entities": [{"local_id": "p1", "name": "令狐冲", "type": "Person", "aliases": []}],
        "facts": [],
        "attributes": [{
            "entity_local_id": "p1", "property_id": "master", "value": "岳不群",
            "evidence": {"start": 0, "end": 3, "quote": "令狐冲"}, "confidence": 0.9,
        }],
    })
    normalized = normalize_chunk_result("p-1", chunk, result)
    assert normalized.entities
    assert normalized.attributes == []
    assert [item.code for item in normalized.rejections] == ["UNKNOWN_ENTITY_PROPERTY"]
```

Also test `EMPTY_ATTRIBUTE_VALUE`, `UNKNOWN_ATTRIBUTE_ENTITY`, `INVALID_ATTRIBUTE_ENUM`, `INVALID_ATTRIBUTE_NUMBER`, `INVALID_ATTRIBUTE_BOOLEAN`, `ATTRIBUTE_EVIDENCE_MISMATCH`, and `ATTRIBUTE_EVIDENCE_TOO_LONG`.

- [ ] **Step 2: Run normalization tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/extraction/test_normalize.py apps/api/tests/extraction/test_attribute_pipeline.py -q
```

Expected: failures because normalized attributes and graph records do not exist.

- [ ] **Step 3: Add attribute records and normalization**

Add:

```python
class AttributeAssertionRecord(BaseModel):
    id: str
    entity_id: str
    entity_name: str
    entity_type: EntityType
    property_id: str
    value: str
    value_type: PropertyValueType
    confidence: float = Field(default=1.0, ge=0, le=1)
    evidence_ids: list[str] = Field(min_length=1)
```

`entity_name` and `entity_type` are import hints for resolving canonical existing entities during backfill. Generate the assertion ID from normalized value text and merge evidence IDs for duplicate assertions. Reuse `_aligned_evidence_range()` and create only one `EvidenceRecord` per unique quote position.

- [ ] **Step 4: Add attributes to pipeline aggregation and quality**

Aggregate duplicate assertions by stable ID using the same evidence-union pattern as facts. Populate the ontology request with effective property definitions. Add attributes to `GraphDocument`, `ImportSummary`, and the quality report.

- [ ] **Step 5: Run extraction pipeline tests**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/extraction -q
```

Expected: all extraction tests pass.

- [ ] **Step 6: Commit normalization**

```bash
git add apps/api/src/app/extraction apps/api/src/app/graph/models.py apps/api/tests/extraction
git commit -m "feat: normalize evidence-backed entity attributes"
```

---

### Task 4: Import Attribute Assertions Idempotently into Neo4j

**Files:**
- Modify: `apps/api/src/app/graph/importer.py`
- Modify: `apps/api/src/app/graph/neo4j.py`
- Modify: `apps/api/tests/graph/test_importer.py`
- Test: `apps/api/tests/graph/test_live_api.py`

**Interfaces:**
- Consumes: `GraphDocument.attributes` from Task 3.
- Produces: `Neo4jGraphWriter.upsert_batch("AttributeAssertion", rows)` and the `HAS_ATTRIBUTE` / `EVIDENCED_BY` graph shape.
- Consumed by: Tasks 6 and 8.

- [ ] **Step 1: Write failing importer idempotency test**

Extend `sample_document()` with one assertion and assert first import creates one assertion while the second creates zero. Also assert the writer receives `AttributeAssertion` after `Entity` and `Evidence`.

```python
assert first.created_attributes == 1
assert second.created_attributes == 0
assert fake_graph.count("AttributeAssertion") == 1
```

- [ ] **Step 2: Run importer tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/graph/test_importer.py -q
```

Expected: failure because importer does not send attribute rows.

- [ ] **Step 3: Add constraints, indexes, and attribute upsert Cypher**

Add to `CONSTRAINTS`:

```cypher
CREATE CONSTRAINT attribute_assertion_id IF NOT EXISTS
FOR (n:AttributeAssertion) REQUIRE (n.project_id, n.id) IS UNIQUE
```

Add to a new `INDEXES` tuple:

```cypher
CREATE INDEX entity_project_name IF NOT EXISTS FOR (n:Entity) ON (n.project_id, n.name)
CREATE INDEX entity_project_type IF NOT EXISTS FOR (n:Entity) ON (n.project_id, n.type)
```

Add `AttributeAssertion` upsert logic that first matches the canonical entity by stable ID, then falls back to exact `name` or alias within the same project. If no canonical entity exists, skip the row. Merge the assertion, `HAS_ATTRIBUTE`, and every `EVIDENCED_BY` edge. Never create an entity from an attribute-only import.

- [ ] **Step 4: Import attributes after evidence**

Call:

```python
created_attributes = self.writer.upsert_batch(
    "AttributeAssertion",
    [{"project_id": project_id, **item.model_dump(mode="json")} for item in document.attributes],
)
```

Return the count in `ImportSummary`.

- [ ] **Step 5: Run graph importer tests**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/graph/test_importer.py apps/api/tests/graph/test_live_api.py -q
```

Expected: unit tests pass; live tests pass when Neo4j is available or remain skipped according to their existing marker behavior.

- [ ] **Step 6: Commit graph persistence**

```bash
git add apps/api/src/app/graph apps/api/tests/graph
git commit -m "feat: persist attribute assertions in neo4j"
```

---

### Task 5: Add Backward-Compatible Job Kinds and Attribute Job API

**Files:**
- Modify: `apps/api/src/app/jobs/models.py`
- Modify: `apps/api/src/app/jobs/repository.py`
- Modify: `apps/api/src/app/jobs/router.py`
- Modify: `apps/api/src/app/projects/router.py`
- Modify: `apps/api/tests/jobs/test_repository.py`
- Create: `apps/api/tests/jobs/test_attribute_jobs.py`
- Modify: `apps/api/tests/projects/test_router.py`

**Interfaces:**
- Produces: `JobKind`, `Job.kind`, `JobRepository.create(project_id, model_profile_id, kind=JobKind.FULL_BUILD)`, `JobSnapshot.kind`, and `POST /api/projects/{project_id}/attribute-jobs`.
- Consumed by: Tasks 6 and 10.

- [ ] **Step 1: Write failing SQLite migration test**

Create a legacy `jobs` table without `kind`, initialize `JobRepository`, and assert the new column and default:

```python
columns = {column["name"] for column in inspect(engine).get_columns("jobs")}
assert "kind" in columns
assert repository.get(job_id).kind == JobKind.FULL_BUILD
```

- [ ] **Step 2: Write failing API tests**

Test successful creation, unknown project, missing source, and unknown profile:

```python
response = client.post(
    f"/api/projects/{user_project.id}/attribute-jobs",
    json={"model_profile_id": "fixed:test"},
)
assert response.status_code == 201
assert response.json()["kind"] == "ATTRIBUTE_BACKFILL"
```

- [ ] **Step 3: Run the job tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/jobs apps/api/tests/projects/test_router.py -q
```

Expected: failures for missing job kind and endpoint.

- [ ] **Step 4: Implement the job kind and SQLite upgrade**

Add:

```python
class JobKind(StrEnum):
    FULL_BUILD = "FULL_BUILD"
    ATTRIBUTE_BACKFILL = "ATTRIBUTE_BACKFILL"
```

Add a non-null `kind` column with application default `FULL_BUILD`. In `JobRepository.__init__`, inspect SQLite columns after `create_all()`. If missing, execute:

```sql
ALTER TABLE jobs ADD COLUMN kind VARCHAR(30) NOT NULL DEFAULT 'FULL_BUILD'
```

Include `kind` in events and `JobSnapshot`.

- [ ] **Step 5: Implement the attribute-job endpoint**

Add `AttributeJobRequest(model_profile_id: str)` and validate project, `source_path`, and model profile before calling:

```python
jobs.create(project_id, request.model_profile_id, JobKind.ATTRIBUTE_BACKFILL)
```

Return `404 PROJECT_NOT_FOUND`, `409 PROJECT_SOURCE_MISSING`, or `422 UNKNOWN_MODEL_PROFILE` with the existing structured error style.

- [ ] **Step 6: Run job and project tests**

Run the Task 5 pytest command again. Expected: all selected tests pass.

- [ ] **Step 7: Commit attribute jobs**

```bash
git add apps/api/src/app/jobs apps/api/src/app/projects/router.py apps/api/tests/jobs apps/api/tests/projects/test_router.py
git commit -m "feat: add attribute backfill jobs"
```

---

### Task 6: Route Worker Jobs to Attribute-Only Import

**Files:**
- Modify: `apps/api/src/app/extraction/pipeline.py`
- Modify: `apps/api/src/app/graph/importer.py`
- Modify: `apps/api/src/app/worker/online.py`
- Modify: `apps/api/tests/extraction/test_pipeline.py`
- Modify: `apps/api/tests/worker/test_runner.py`

**Interfaces:**
- Consumes: `Job.kind`, normalized attributes, and Neo4j attribute upsert.
- Produces: `ExtractionPipeline.process(project_id: str, title: str, source: str, provider: ExtractionProvider, *, attributes_only: bool = False) -> PipelineResult` and `GraphImporter.import_attributes(document: GraphDocument) -> ImportSummary`.
- Consumed by: Task 10.

- [ ] **Step 1: Write failing worker isolation test**

Create a `JobKind.ATTRIBUTE_BACKFILL` job and a recording writer. Run all five stages and assert that `Project`, `Chapter`, `Entity`, and `Fact` batches are not written, while `Evidence` and `AttributeAssertion` are written.

```python
assert set(writer.labels) <= {"Evidence", "AttributeAssertion"}
assert jobs.get(job.id).status == JobStatus.COMPLETED
```

- [ ] **Step 2: Run worker and pipeline tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/worker/test_runner.py apps/api/tests/extraction/test_pipeline.py -q
```

Expected: failure because worker ignores `job.kind`.

- [ ] **Step 3: Add attribute-only import mode**

Keep one extraction loop so retry, content filtering, evidence validation, and quality counts cannot drift. When `attributes_only=True`, call `GraphImporter.import_attributes()` and exclude facts/entities from the import summary. `import_attributes()` must upsert only evidence that is referenced by accepted attributes and then the assertions.

- [ ] **Step 4: Route by job kind**

In `_build()`:

```python
attributes_only = JobKind(job.kind) == JobKind.ATTRIBUTE_BACKFILL
result = self.pipeline.process(
    project.id,
    project.title,
    source,
    self.providers.create(job.model_profile_id),
    attributes_only=attributes_only,
)
```

Preserve current job status transitions and quality storage.

- [ ] **Step 5: Run worker and extraction tests**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/worker apps/api/tests/extraction -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit worker routing**

```bash
git add apps/api/src/app/extraction/pipeline.py apps/api/src/app/graph/importer.py apps/api/src/app/worker/online.py apps/api/tests/extraction apps/api/tests/worker
git commit -m "feat: backfill attributes without rebuilding graph"
```

---

### Task 7: Reuse Neo4j Driver and Optimize Search and One-Hop Queries

**Files:**
- Modify: `apps/api/src/app/main.py`
- Modify: `apps/api/src/app/graph/router.py`
- Modify: `apps/api/src/app/graph/repository.py`
- Modify: `apps/api/src/app/graph/service.py`
- Modify: `apps/api/tests/graph/test_router.py`
- Modify: `apps/api/tests/graph/test_service.py`

**Interfaces:**
- Produces: application-lifespan `app.state.neo4j_driver`, request-scoped repository wrappers over the shared Driver, `search_exact`, `search_contains`, and a one-query depth-1 neighborhood path.
- Consumed by: Tasks 8 and 9; QA continues to consume `get_repository` unchanged.

- [ ] **Step 1: Write failing service tests for exact-first search**

Use a fake repository recording calls:

```python
results = GraphService(repository).search("p-1", "令狐冲", [], 20)
assert repository.calls == ["exact", "contains"]
assert results[0].name == "令狐冲"
assert len({item.id for item in results}) == len(results)
```

Also test that exact results satisfying the limit skip the contains query.

- [ ] **Step 2: Write failing one-hop test proving no existence round trip**

Use a repository that only implements `neighborhood()` and assert `GraphService.neighborhood("p-1", "linghu", 1, 50, None, None)` succeeds. A missing center is reported by `repository.neighborhood()` returning `None`, which the service maps to `EntityNotFoundError`.

- [ ] **Step 3: Run graph tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/graph/test_service.py apps/api/tests/graph/test_router.py -q
```

Expected: failures because the current service calls `entity_exists` and the repository has a single scan-based search.

- [ ] **Step 4: Implement exact-first indexed search**

Add an exact query using `n.project_id = $project_id AND n.name = $search_text`, which can use the composite index. If fewer than `limit` rows are found, run the existing name/alias contains query for the remaining capacity. Deduplicate by `id`, preserve exact-first order, filter merged entities in both paths, and validate project isolation in the service.

- [ ] **Step 5: Implement dedicated one-hop Cypher**

For `depth == 1`, use `MATCH center` plus `OPTIONAL MATCH` directly over `RELATED`. Apply review and chapter filters before collecting and limiting edges. Always return the center node even if it has no relations. Retain the existing bounded variable-length query only for `depth == 2`.

- [ ] **Step 6: Add FastAPI Driver lifespan**

Create the Driver once in `main.py`:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    driver = GraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
    app.state.neo4j_driver = driver
    try:
        yield
    finally:
        driver.close()


app = FastAPI(title="江湖图谱 API", lifespan=lifespan)
```

Change `get_repository(request: Request)` to wrap `request.app.state.neo4j_driver` without closing it. Preserve dependency overrides used by tests and QA.

- [ ] **Step 7: Run graph and QA tests**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/graph apps/api/tests/qa -q
```

Expected: all non-live tests pass; live tests follow their current environment behavior.

- [ ] **Step 8: Commit graph performance backend**

```bash
git add apps/api/src/app/main.py apps/api/src/app/graph apps/api/tests/graph apps/api/tests/qa
git commit -m "perf: optimize graph search and one-hop queries"
```

---

### Task 8: Enrich Entity Detail with Attributes and Relation Summaries

**Files:**
- Modify: `apps/api/src/app/graph/models.py`
- Modify: `apps/api/src/app/graph/repository.py`
- Modify: `apps/api/src/app/graph/service.py`
- Modify: `apps/api/tests/graph/test_service.py`
- Modify: `apps/api/tests/graph/test_router.py`

**Interfaces:**
- Consumes: ontology property labels and persisted attribute assertions.
- Produces: `AttributeDetail`, `RelationSummary`, `EntityDetail.attributes`, and `EntityDetail.relations`.
- Consumed by: Tasks 9 and 10.

- [ ] **Step 1: Write failing entity-detail contract test**

Provide repository rows for one attribute and one relation, then assert:

```python
detail = GraphService(repository).entity_detail("p-1", "linghu")
assert detail.attributes[0].property_id == "identity"
assert detail.attributes[0].label == "身份"
assert detail.attributes[0].value == "华山派大弟子"
assert detail.relations[0].other.name == "岳不群"
assert detail.relations[0].direction == "INCOMING"
assert detail.facts[0].evidence[0].quote
```

- [ ] **Step 2: Run entity detail tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/graph/test_service.py apps/api/tests/graph/test_router.py -q
```

Expected: model validation failure for missing attribute and relation contracts.

- [ ] **Step 3: Add additive response models**

Define:

```python
class AttributeDetail(BaseModel):
    id: str
    property_id: str
    label: str
    value_type: str
    value: str
    confidence: float = 1.0
    evidence: list[EvidenceDetail] = Field(default_factory=list)


class RelationEntity(BaseModel):
    id: str
    type: str
    name: str


class RelationSummary(BaseModel):
    fact_id: str
    type: str
    label: str
    direction: Literal["OUTGOING", "INCOMING"]
    other: RelationEntity
```

Add empty-list defaults to `EntityDetail`.

- [ ] **Step 4: Query attributes and facts in separate Cypher subqueries**

Use one `CALL` subquery that starts from `entity-[:HAS_ATTRIBUTE]->attribute`, matches the attribute evidence, and returns collected attribute rows. Use a second `CALL` subquery that starts from `fact-[:SOURCE|TARGET]->entity`, matches fact endpoints and evidence, and returns collected fact rows. Keeping the aggregations separate prevents multiple evidence matches from multiplying each other. Filter rejected facts and merged entities. Resolve labels in `GraphService` from the ontology catalog. Deduplicate evidence IDs within each attribute and fact.

- [ ] **Step 5: Run graph detail tests**

Run the Task 8 pytest command again. Expected: all selected tests pass.

- [ ] **Step 6: Commit enriched details**

```bash
git add apps/api/src/app/graph apps/api/tests/graph
git commit -m "feat: expose entity attributes and relation summaries"
```

---

### Task 9: Render the Center Immediately and Load One Hop Independently

**Files:**
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/features/graph/GraphPage.tsx`
- Modify: `apps/web/src/features/graph/GraphCanvas.tsx`
- Modify: `apps/web/src/features/graph/GraphPage.test.tsx`

**Interfaces:**
- Consumes: existing search, one-hop neighborhood, two-hop neighborhood, and entity-detail APIs.
- Produces: abort-aware `apiFetch`, independent graph/detail state, immediate center rendering, and on-demand two-hop expansion.
- Consumed by: Task 10.

- [ ] **Step 1: Write failing staged-loading tests**

Use deferred promises to prove graph ordering:

```typescript
await user.click(await screen.findByRole('button', { name: /令狐冲/ }))
expect(screen.getByLabelText('知识图谱画布')).toHaveTextContent('令狐冲')

neighborhood.resolve(json({ nodes: [entity, yue], edges: [edge] }))
expect(await screen.findByText('岳不群')).toBeVisible()
expect(screen.queryByText('华山派大弟子')).not.toBeInTheDocument()

detail.resolve(json({ ...entity, attributes: [identity], relations: [], facts: [] }))
expect(await screen.findByText('华山派大弟子')).toBeVisible()
```

Add tests for `depth=1` initial request, `depth=2` only after clicking “展开二度关系”, stale request cancellation, and preserving the one-hop graph when two-hop expansion fails.

- [ ] **Step 2: Run GraphPage tests and verify failure**

Run:

```bash
npm --prefix apps/web test -- --run src/features/graph/GraphPage.test.tsx
```

Expected: failures because the current code waits on `Promise.all` and requests depth 2 immediately.

- [ ] **Step 3: Make `apiFetch` abort-aware**

Keep the existing `RequestInit` signature and allow callers to pass `signal`. If the response is not OK, preserve the current user-facing error. Callers identify `DOMException` with name `AbortError` and suppress it.

- [ ] **Step 4: Split graph and detail request state**

On select:

```typescript
setGraph({ nodes: [selectedEntity], edges: [] })
setDetail(undefined)
setGraphLoading(true)
setDetailLoading(true)
```

Start independent requests. Apply neighborhood as soon as it resolves; apply detail separately. Store the selected `EntitySummary`, depth, and two controllers in refs. Abort both controllers when project changes, a new entity is selected, or the component unmounts.

- [ ] **Step 5: Add on-demand two-hop expansion**

Render a button only after a one-hop graph is loaded. Request `depth=2&limit=100`, keep the existing graph visible during loading, replace it on success, and retain it plus show a retryable error on failure.

- [ ] **Step 6: Replace iterative layout**

Change Cytoscape layout to `concentric` with the selected center node assigned the highest concentric value. Pass `centerId` into `GraphCanvas`. Render accessible node labels in a visually hidden list so component tests and screen readers can observe graph content without depending on canvas internals.

- [ ] **Step 7: Run frontend graph tests and typecheck**

Run:

```bash
npm --prefix apps/web test -- --run src/features/graph/GraphPage.test.tsx
npm --prefix apps/web run typecheck
```

Expected: tests and typecheck pass.

- [ ] **Step 8: Commit staged graph loading**

```bash
git add apps/web/src/api/client.ts apps/web/src/features/graph
git commit -m "perf: render one-hop graph without waiting for details"
```

---

### Task 10: Display Attributes and Add the Backfill UI

**Files:**
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/features/graph/EntityPanel.tsx`
- Modify: `apps/web/src/features/graph/GraphPage.tsx`
- Modify: `apps/web/src/features/graph/GraphPage.test.tsx`
- Create: `apps/web/src/features/build/AttributeBackfill.tsx`
- Modify: `apps/web/src/features/build/BuildPage.tsx`
- Modify: `apps/web/src/features/build/QualityReport.tsx`
- Modify: `apps/web/src/features/build/BuildPage.test.tsx`
- Modify: `apps/web/src/styles/theme.css`

**Interfaces:**
- Consumes: `EntityDetail.attributes`, `EntityDetail.relations`, `JobSnapshot.kind`, and the attribute-job endpoint.
- Produces: approved entity panel layout and an existing-project “重新抽取属性” workflow.

- [ ] **Step 1: Write failing entity panel tests**

Assert the approved order and empty state:

```typescript
expect(await screen.findByRole('heading', { name: '本体属性' })).toBeVisible()
expect(screen.getByText('身份')).toBeVisible()
expect(screen.getByText('华山派大弟子')).toBeVisible()
expect(screen.getByRole('heading', { name: '关系摘要' })).toBeVisible()
expect(screen.getByText('岳不群')).toBeVisible()
expect(screen.getByText('属性证据')).toBeVisible()
```

For an empty array, assert “尚未抽取到有证据支持的属性”.

- [ ] **Step 2: Write failing backfill form tests**

Render `BuildPage` on an existing project. Assert the button is enabled when `source_size` is present, the request body contains the selected profile, and the returned job appears in `JobProgress`. Assert the button is disabled with “原始 TXT 不可用” when `source_size` is absent.

- [ ] **Step 3: Run frontend tests and verify failure**

Run:

```bash
npm --prefix apps/web test -- --run src/features/graph/GraphPage.test.tsx src/features/build/BuildPage.test.tsx
```

Expected: failures because attributes, relation summaries, and backfill controls do not render.

- [ ] **Step 4: Add frontend API types**

Add `AttributeDetail`, `RelationSummary`, `JobKind`, attribute quality fields, and empty-array-safe defaults at component boundaries. Keep existing fields unchanged.

- [ ] **Step 5: Implement the approved entity panel**

Render sections in this order: identity, ontology attributes, relation summary, attribute evidence, relation evidence. Group repeated values by property label. Show chapter, quote, and offsets for each attribute assertion. Preserve the existing “加入审核” button only for relation facts.

- [ ] **Step 6: Implement `AttributeBackfill`**

Accept `project`, `profiles`, and `onCreated(job)`. POST JSON to `/api/projects/{id}/attribute-jobs`. Disable while busy, when no profile is selected, or when `project.source_size` is absent. Use the current project from `ProjectContext`; do not create a second project.

- [ ] **Step 7: Integrate task progress and quality metrics**

Set the build URL `project` and `job` parameters to the returned job. Reuse `JobProgress`. For `ATTRIBUTE_BACKFILL`, label the stages as attribute extraction/import without changing backend statuses. Add “属性”和“属性证据” metrics when those fields are present; retain existing metrics for full builds.

- [ ] **Step 8: Style the approved layout**

Extend existing `entity-panel`, `aliases`, `blockquote`, and build form styles. Use existing theme variables and responsive behavior. Do not introduce a new visual system or fixed-width viewport assumptions.

- [ ] **Step 9: Run all frontend tests and build**

Run:

```bash
npm --prefix apps/web test -- --run
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

Expected: all frontend tests, typecheck, and production build pass.

- [ ] **Step 10: Commit the UI**

```bash
git add apps/web/src
git commit -m "feat: show entity attributes and backfill controls"
```

---

### Task 11: Add Performance Verification and Deployment Operations

**Files:**
- Create: `scripts/check-graph-performance.py`
- Modify: `docs/deployment-docker-azure-openai.md`
- Modify: `README.md`

**Interfaces:**
- Consumes: deployed graph API.
- Produces: a repeatable command that measures search, one-hop, detail, and two-hop requests without external packages.

- [ ] **Step 1: Add a failing CLI smoke check specification**

Document the expected command before implementation:

```bash
python3 scripts/check-graph-performance.py \
  --base-url http://localhost:5173 \
  --project-id xiaoao \
  --query 令狐冲
```

Expected output contains the following keys with numeric millisecond values and the selected entity ID:

```text
search_p50_ms=120.0
search_p95_ms=180.0
one_hop_ms=240.0
detail_ms=360.0
two_hop_ms=520.0
entity_id=xiaoao:Person:example
```

The command exits non-zero when search returns no entity or any request fails. It prints warnings, not failures, when environment-dependent budgets are exceeded.

- [ ] **Step 2: Implement the standard-library timing script**

Use `argparse`, `urllib.parse`, `urllib.request`, `json`, and `time.perf_counter`. Select the exact-name result first, then the first result as fallback. Make one warm-up search followed by five measured searches and one measured call for each remaining endpoint. Print median and P95 for repeated calls.

- [ ] **Step 3: Document deployment and backfill operations**

Add:

```bash
git pull
sudo docker compose up -d --build --wait
python3 scripts/check-graph-performance.py --base-url http://localhost:5173 --project-id xiaoao --query 令狐冲
```

Document the UI backfill action, how to monitor `worker` logs, that backfill preserves graph facts, and how to back up both Docker volumes before the first production backfill.

- [ ] **Step 4: Run final backend verification**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests -q
```

Expected: all non-live backend tests pass; any live-test skip must be explicit in pytest output rather than hidden by excluding tests.

- [ ] **Step 5: Run final frontend verification**

Run:

```bash
npm --prefix apps/web test -- --run
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
git diff --check
```

Expected: all commands exit 0.

- [ ] **Step 6: Run Docker and browser verification**

Run:

```bash
sudo docker compose up -d --build --wait
docker compose ps
python3 scripts/check-graph-performance.py --base-url http://localhost:5173 --project-id xiaoao --query 令狐冲
```

In a real browser, verify: center-first rendering, one-hop load, two-hop expansion, attributes, relation summary, both evidence sections, project switching, backfill task progress, and responsive panel layout.

- [ ] **Step 7: Commit operations documentation**

```bash
git add scripts/check-graph-performance.py docs/deployment-docker-azure-openai.md README.md
git commit -m "docs: add attribute backfill and graph performance checks"
```

---

## Final Review Gate

- [ ] Confirm every design requirement maps to at least one task.
- [ ] Confirm no existing API response field was removed or changed incompatibly.
- [ ] Confirm backfill cannot create projects, entities, or facts.
- [ ] Confirm attributes without valid evidence never reach Neo4j.
- [ ] Confirm graph rendering does not wait for entity details.
- [ ] Confirm one-hop is the default and two-hop requires explicit user action.
- [ ] Confirm SQLite schema upgrade succeeds against an existing data volume.
- [ ] Confirm no credentials, uploaded novel text, database files, or `.env` files are staged.
- [ ] Confirm `git status --short` is clean after all commits.
