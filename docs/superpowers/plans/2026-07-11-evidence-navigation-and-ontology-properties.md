# Evidence Navigation and Ontology Properties Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make graph relationships and entity attributes clickable evidence links and let ontology type cards reveal their effective property definitions.

**Architecture:** Add a project-scoped relation-evidence read path backed by the existing Fact/EVIDENCED_BY graph. Keep evidence scrolling and selected-state coordination in `GraphPage`/`EntityPanel`, while `GraphCanvas` only emits edge clicks and styles the selected edge. Extend the existing ontology response typing and render effective property definitions locally without changing the ontology data model.

**Tech Stack:** FastAPI, Pydantic v2, Neo4j, pytest, React/TypeScript, Vitest, Cytoscape.

## Global Constraints

- Relation evidence must be restricted by `project_id` and omit rejected relations and merged entities.
- Attribute evidence continues to come from the existing entity-detail payload.
- No changes to entity, fact, attribute assertion, evidence, or ontology persistence schemas.
- Project changes and entity-panel close must clear selected relation, selected attribute, and loaded relation evidence.
- Existing graph search, entity detail, review, ontology, and project-switch behavior must remain functional.

---

### Task 1: Add project-scoped relation evidence API

**Files:**
- Modify: `apps/api/src/app/graph/models.py`
- Modify: `apps/api/src/app/graph/repository.py`
- Modify: `apps/api/src/app/graph/service.py`
- Modify: `apps/api/src/app/graph/router.py`
- Test: `apps/api/tests/graph/test_service.py`
- Test: `apps/api/tests/graph/test_router.py`

**Interfaces:**
- `Neo4jGraphRepository.relation_detail(project_id: str, relation_id: str) -> dict[str, Any] | None`.
- `GraphService.relation_detail(project_id: str, relation_id: str) -> RelatedFact`.
- `GET /api/graph/relations/{relation_id}?project_id=<id>` returns `RelatedFact`.

- [ ] **Step 1: Write failing repository/service tests.** Add a fake relation with `source_id`, `target_id`, `type`, `review_status`, and two evidence rows. Assert the service returns both evidence entries, rejects a `REJECTED` relation, and returns `EntityNotFoundError`/404 for a missing relation.
- [ ] **Step 2: Run the focused tests.** Run `pytest apps/api/tests/graph/test_service.py apps/api/tests/graph/test_router.py -q`; expect the new tests to fail because no relation-detail method or route exists.
- [ ] **Step 3: Implement the repository query.** Match `Fact {project_id, id: $relation_id}` and its source/target entities; filter merged entities and rejected facts; optionally match all `EVIDENCED_BY`/`IN_CHAPTER` evidence; return one normalized row with an evidence list.
- [ ] **Step 4: Implement service/model/route.** Reuse `RelatedFact` and `EvidenceDetail`, map the row through Pydantic, and route through existing `execute` so missing relations become `ENTITY_NOT_FOUND` and Neo4j failures become `GRAPH_UNAVAILABLE`.
- [ ] **Step 5: Run focused tests.** Run the same pytest command; expect all pass.
- [ ] **Step 6: Commit.** Run `git add apps/api/src/app/graph/models.py apps/api/src/app/graph/repository.py apps/api/src/app/graph/service.py apps/api/src/app/graph/router.py apps/api/tests/graph/test_service.py apps/api/tests/graph/test_router.py && git commit -m "feat: expose relation evidence lookup"`.

### Task 2: Add graph edge selection and evidence scrolling

**Files:**
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/features/graph/GraphCanvas.tsx`
- Modify: `apps/web/src/features/graph/EntityPanel.tsx`
- Modify: `apps/web/src/features/graph/GraphPage.tsx`
- Test: `apps/web/src/features/graph/GraphPage.test.tsx`

**Interfaces:**
- Add `RelationEvidence` client type matching `RelatedFact`.
- `GraphCanvas` receives `selectedRelationId?: string` and `onSelectEdge: (edgeId: string) => void`.
- `EntityPanel` receives `selectedRelationId`, `selectedAttributeId`, `relationEvidence`, `relationEvidenceLoading`, `onSelectRelation`, and `onSelectAttribute`.

- [ ] **Step 1: Write failing UI tests.** Mock `/api/graph/relations/:id`; assert clicking an edge calls that endpoint, highlights the relation evidence, clicking a relation summary scroll target changes the selected state, and clicking an attribute row scrolls to its evidence target.
- [ ] **Step 2: Run `npm --prefix apps/web test -- --run src/features/graph/GraphPage.test.tsx`; expect the new interaction tests to fail.**
- [ ] **Step 3: Implement `GraphCanvas` edge events and styling.** Register Cytoscape `tap` for `edge`, call `onSelectEdge(edge.id)`, and add a selected-edge style with increased width and accent colors. Preserve existing node selection and abort behavior.
- [ ] **Step 4: Implement `GraphPage` selection state and loading.** Add selected relation/attribute state, fetch `/api/graph/relations/${id}?project_id=${projectId}`, ignore stale responses with the existing abort pattern, and clear all selection state on project change/entity close.
- [ ] **Step 5: Implement `EntityPanel` anchors and scrolling.** Render stable IDs for relation rows and evidence cards, make relation/attribute rows buttons, call `scrollIntoView({block: 'nearest'})`, and apply a temporary highlight class. Show relation evidence loading/error states without clearing entity details.
- [ ] **Step 6: Run graph tests and frontend checks.** Run `npm --prefix apps/web test -- --run src/features/graph/GraphPage.test.tsx`, `npm --prefix apps/web run typecheck`, and `npm --prefix apps/web run build`; expect all pass.
- [ ] **Step 7: Commit.** Run `git add apps/web/src/api/client.ts apps/web/src/features/graph/GraphCanvas.tsx apps/web/src/features/graph/EntityPanel.tsx apps/web/src/features/graph/GraphPage.tsx apps/web/src/features/graph/GraphPage.test.tsx && git commit -m "feat: navigate graph selections to evidence"`.

### Task 3: Expand ontology type cards with effective properties

**Files:**
- Modify: `apps/web/src/api/client.ts`
- Modify: `apps/web/src/features/ontology/OntologyPage.tsx`
- Test: `apps/web/src/features/ontology/OntologyPage.test.tsx`

**Interfaces:**
- Extend `OntologyCatalog.entity_types` with `property_definitions` and `effective_property_definitions` containing `id`, `label`, `description`, `value_type`, `multiple`, and `enum_values`.
- `OntologyPage` owns `expandedTypeId: string | undefined` and renders effective definitions for the selected type.

- [ ] **Step 1: Write failing ontology tests.** Mock the catalog with `Person` and child `Sect`; assert clicking a type card expands the property definition list, displays value type/multiple/description, and shows inherited properties on the child.
- [ ] **Step 2: Run `npm --prefix apps/web test -- --run src/features/ontology/OntologyPage.test.tsx`; expect failure because cards are not interactive and the client type omits properties.**
- [ ] **Step 3: Extend the client type and card rendering.** Make cards buttons or keyboard-accessible articles, toggle one expanded type at a time, and render a compact property table with inherited/source labels. Preserve TBox/ABox tabs and current visual hierarchy.
- [ ] **Step 4: Run the ontology tests and typecheck.** Expect all pass.
- [ ] **Step 5: Commit.** Run `git add apps/web/src/api/client.ts apps/web/src/features/ontology/OntologyPage.tsx apps/web/src/features/ontology/OntologyPage.test.tsx && git commit -m "feat: show ontology class properties"`.

### Task 4: Full regression verification and delivery

**Files:**
- Modify: none unless a targeted regression is found

- [ ] **Step 1: Start a temporary Neo4j container for integration tests.** Run `docker compose up -d neo4j` and wait for `docker compose ps` to report healthy.
- [ ] **Step 2: Run complete backend tests.** Run `/Users/yonglun/Repo/tspw-graph/.venv/bin/python -m pytest apps/api/tests -q`; expect no new failures and only documented skips.
- [ ] **Step 3: Run complete frontend checks.** Run `npm --prefix apps/web test -- --run`, `npm --prefix apps/web run typecheck`, and `npm --prefix apps/web run build`.
- [ ] **Step 4: Run `git diff --check` and `git status --short`; expect clean intentional changes.**
- [ ] **Step 5: Stop only the temporary test container and preserve unrelated user services.** Run `docker compose down` only for the compose project started by this work.
- [ ] **Step 6: Commit any targeted verification fixes, then use the finishing-a-development-branch workflow to choose merge, PR, keep, or discard.**

