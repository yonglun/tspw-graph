# Final Review Fixes Report

## Status

Implemented all seven final-review fixes with regression-first RED/GREEN cycles. No design, plan, or brief files were modified. Backward-compatible fields were added to `ImportSummary`; existing fields and endpoint contracts remain unchanged.

## Fix 1-2: Canonical entity resolution before evidence writes

### RED

Command:

```bash
/Users/yonglun/Repo/tspw-graph/.venv/bin/python -m pytest apps/api/tests/graph/test_importer.py -q
```

Observed: `5 failed, 2 passed`. The failures proved that unresolved assertions and their evidence were retained, alias assertions kept transient IDs, canonical/alias assertions did not converge, the upsert query still selected a fallback candidate, and no resolution interface existed.

A separate quality regression test failed with `accepted_attributes == 1` instead of `0` after resolution rejected the assertion.

### GREEN

- Added atomic `GraphWriter.upsert_attribute_bundle(...)` behavior and an explicit implementation on every fake.
- Stable same-type, non-merged ID matches take priority.
- Exact existing name/alias fallback is retained only when `size(candidates) = 1`; ambiguous and missing matches return no mapping.
- `GraphImporter` passes only attribute-bearing entity hints plus raw attribute/evidence rows to the atomic writer. The Neo4j transaction resolves and write-locks canonical entities, recomputes assertion IDs, merges convergent evidence IDs, filters evidence, and writes evidence/assertions before committing.
- Full builds resolve after entity upsert; backfills never upsert entities or facts.
- Added retained assertion/evidence counts to `ImportSummary` so quality reports describe accepted rows, not pre-resolution candidates.

Focused result: importer tests GREEN, then the complete backend gate passed.

Files:

- `apps/api/src/app/graph/importer.py`
- `apps/api/src/app/graph/neo4j.py`
- `apps/api/src/app/graph/models.py`
- `apps/api/src/app/extraction/pipeline.py`
- `apps/api/tests/graph/test_importer.py`
- `apps/api/tests/extraction/test_pipeline.py`
- `apps/api/tests/extraction/test_attribute_pipeline.py`
- `apps/api/tests/worker/test_runner.py`

## Fix 3-4: Bound graph queries and preserve center semantics

### RED

Command:

```bash
/Users/yonglun/Repo/tspw-graph/.venv/bin/python -m pytest apps/api/tests/graph/test_service.py -k 'one_hop_query_returns or depth_two' -q
```

Observed: `3 failed`. Neither query used a limiting subquery; depth two matched the path and center together, so an isolated center could not be distinguished from a missing center.

### GREEN

- Both depths match and validate the center before a `CALL` subquery.
- One-hop rows are ordered and limited before `collect(edge)`/`collect(other)`.
- Two-hop paths are deterministically ordered and limited before `collect(path)`.
- A valid isolated center returns `[center]`; a missing/merged center returns no record and remains a 404.
- Existing post-query unique-node cap and trimmed-edge removal remain in place.

Focused result: `3 passed`.

Files: `apps/api/src/app/graph/repository.py`, `apps/api/tests/graph/test_service.py`.

## Fix 5: Clear graph state on project switch

### RED

Command:

```bash
npm --prefix apps/web test -- --run src/features/graph/GraphPage.test.tsx -t 'clears graph and entity state'
```

Observed: `1 failed`; the old `岳不群` node remained after switching the router project parameter.

### GREEN

The project-ID effect now aborts entity requests and clears results, graph, detail, selection, depth, loading, and errors. Its dependency list excludes selection, so selecting an entity does not immediately clear it. The component regression proves stale nodes/details disappear and no old entity can expose or issue a two-hop request in the new project.

Focused result: `1 passed`; full web suite: `23 passed`.

Files: `apps/web/src/features/graph/GraphPage.tsx`, `apps/web/src/features/graph/GraphPage.test.tsx`.

## Fix 6: Verify source file before job creation

### RED

Command:

```bash
/Users/yonglun/Repo/tspw-graph/.venv/bin/python -m pytest apps/api/tests/jobs/test_attribute_jobs.py::test_attribute_job_rejects_missing_stored_source_without_creating_job_or_event -q
```

Observed: `1 failed`; the endpoint returned 201 after the stored source had been deleted.

### GREEN

Added traversal-safe stored-path resolution through `UploadStore`, checked `is_file()` before profile validation/job creation, and returned `409 {"detail":{"code":"PROJECT_SOURCE_MISSING"}}` for absent or invalid stored paths. The regression asserts both job and job-event tables remain empty.

Focused result: `5 passed` for `test_attribute_jobs.py`.

Files: `apps/api/src/app/projects/files.py`, `apps/api/src/app/projects/router.py`, `apps/api/tests/jobs/test_attribute_jobs.py`.

## Fix 7: Conservative relationship-semantic validation

### RED

Command:

```bash
/Users/yonglun/Repo/tspw-graph/.venv/bin/python -m pytest apps/api/tests/extraction/test_normalize.py -k 'relationship_semantic or pure_relationship or legitimate_identity' -q
```

Observed: `2 failed, 1 passed`; exact other-entity names/aliases and exact pure roles were accepted, while `华山派大弟子` already remained valid.

### GREEN

Normalization now rejects exact normalized values equal to another accepted candidate entity's canonical name/alias or one of the eight specified pure roles. Checks occur before evidence creation and use equality only, so compound identities are preserved.

Focused result: `3 passed`.

Files: `apps/api/src/app/extraction/normalize.py`, `apps/api/tests/extraction/test_normalize.py`.

## Architectural choices

- Resolution, canonical identity recomputation, evidence selection, writes, and retained counts are one graph-writer transaction because Neo4j owns canonical entity state. The resolver obtains a write lock with a no-op canonical entity `SET`, preventing review merges from interleaving before evidence/assertion persistence.
- Attribute upsert now accepts canonical IDs only and performs no fallback selection, eliminating the evidence-before-resolution race and lexicographic ambiguity.
- `ImportSummary.retained_*` counts separate accepted batch contents from Neo4j `nodes_created`, preserving idempotent created counts while making quality metrics accurate.
- Path safety is centralized in `UploadStore` instead of reconstructing configured-root logic in the endpoint.
- UI cleanup is keyed solely to `projectId`, preserving normal selection behavior.

## Self-review

Reviewed tests first and implementation across correctness, readability, architecture, security, and performance.

- Correctness: all brief invariants have regression coverage; canonical IDs and evidence sets converge; missing/isolated centers differ; job creation is side-effect-free on missing source.
- Readability: resolver responsibilities are separated between writer and importer; no permissive mocks or unrelated refactors were introduced.
- Architecture: existing project/entity/fact/review storage paths remain intact; additions are backward-compatible and localized.
- Security: stored paths are resolved and constrained to the configured upload root.
- Performance: graph result rows are limited inside Cypher before collection; output capping still drops edges touching trimmed nodes.
- Dead code/dependencies: none introduced; no dependency changes.
- Blocking findings after self-review: none.

## Verification

Required commands:

```bash
/Users/yonglun/Repo/tspw-graph/.venv/bin/python -m pytest apps/api/tests/extraction apps/api/tests/graph apps/api/tests/jobs apps/api/tests/projects -q
npm --prefix apps/web test -- --run
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
git diff --check
```

Final run results:

- Backend: `113 passed, 5 skipped`; skips are pre-existing Neo4j-gated tests in `test_live_api.py` and `test_review_filters.py`. No test was newly skipped or disabled.
- Frontend: `23 passed`.
- Typecheck: exit 0.
- Production build: exit 0; 65 modules transformed.
- `git diff --check`: exit 0.

## Concerns

- The current environment has no live Neo4j test service, so the pre-existing Neo4j-gated integration tests remain skipped. Query-contract and fake-driver regressions cover the changed Cypher shape; a live Neo4j integration run remains advisable when that external service is available.

## Follow-up atomicity regression

An independent review identified that resolution, Evidence writes, and AttributeAssertion writes could previously commit in separate transactions. The regression `test_attribute_bundle_resolves_locks_and_writes_in_one_transaction` failed with `AttributeError` before the atomic writer existed. It now proves one `session.execute_write` call contains the locking resolver, Evidence query, and AttributeAssertion query, and that retained counts come from actual transaction result IDs. Focused extraction/graph/worker result: `90 passed, 5 pre-existing skips`; full required backend result: `113 passed, 5 pre-existing skips`.
