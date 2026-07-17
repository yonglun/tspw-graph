# Controlled Extraction Concurrency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add configurable, bounded model-request concurrency to full graph builds and attribute backfills while preserving deterministic graph results, accurate progress, safe cancellation, and all-or-nothing imports.

**Architecture:** `ExtractionPipeline` owns a sliding `ThreadPoolExecutor` window. Worker threads perform only provider calls and per-chunk retries; the main thread records progress, normalizes and merges results in source order, and performs one Neo4j import. `EXTRACTION_CONCURRENCY` defaults to `1`.

**Tech Stack:** Python 3.13, `concurrent.futures`, Pydantic Settings, synchronous HTTPX providers, SQLAlchemy/SQLite, Neo4j, pytest.

## Constraints

- Concurrency range is `1–16`; default is `1`, recommended production starting value is `4`.
- The setting applies to both full graph builds and attribute backfills.
- Only model calls and their per-chunk retries run in worker threads. SQLite writes, normalization, merging, progress persistence, and Neo4j import stay on the main worker thread.
- Results are merged in source-chunk order, regardless of response completion order.
- Fatal errors and cancellation must prevent Neo4j import and partial graph publication.
- Cancellation stops new submissions, cancels queued futures, waits for in-flight requests to finish or time out, and discards their results.
- Do not add async providers, extra worker processes, a cross-process rate limiter, or new dependencies in this change.

## Task 1: Add validated concurrency configuration

**Files:**

- Modify: `apps/api/src/app/settings.py`
- Modify: `apps/api/tests/test_settings_model_profiles.py`
- Modify: `compose.yaml`
- Modify: `.env.example`

- [x] Add failing settings tests for the default, an explicit value, and invalid bounds.

```python
def test_extraction_concurrency_defaults_to_one(monkeypatch):
    monkeypatch.delenv("EXTRACTION_CONCURRENCY", raising=False)
    assert Settings(_env_file=None).extraction_concurrency == 1


def test_extraction_concurrency_reads_environment(monkeypatch):
    monkeypatch.setenv("EXTRACTION_CONCURRENCY", "4")
    assert Settings(_env_file=None).extraction_concurrency == 4


@pytest.mark.parametrize("value", ["0", "-1", "17"])
def test_extraction_concurrency_rejects_out_of_range(monkeypatch, value):
    monkeypatch.setenv("EXTRACTION_CONCURRENCY", value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
```

- [x] Run the focused tests and confirm they fail because the field does not exist.

```bash
.venv/bin/python -m pytest -q apps/api/tests/test_settings_model_profiles.py
```

- [x] Add the validated setting in `Settings`.

```python
extraction_concurrency: int = Field(default=1, ge=1, le=16)
```

- [x] Pass the setting into the shared API/worker Compose environment.

```yaml
EXTRACTION_CONCURRENCY: ${EXTRACTION_CONCURRENCY:-1}
```

- [x] Add `EXTRACTION_CONCURRENCY=1` to `.env.example` with a short comment recommending `4` as the first production tuning value.
- [x] Run the focused tests and validate the rendered Compose configuration.

```bash
.venv/bin/python -m pytest -q apps/api/tests/test_settings_model_profiles.py
docker compose config >/dev/null
```

- [x] Commit this independently reviewable change.

```bash
git add apps/api/src/app/settings.py apps/api/tests/test_settings_model_profiles.py compose.yaml .env.example
git commit -m "feat: configure extraction request concurrency"
```

## Task 2: Implement bounded requests with deterministic merging

**Files:**

- Modify: `apps/api/src/app/extraction/pipeline.py`
- Modify: `apps/api/src/app/worker/main.py`
- Modify: `apps/api/tests/extraction/test_pipeline.py`

- [x] Add test helpers that can return named `TextChunk` instances and providers that record active-call count under a `Lock`.
- [x] Add a failing test with four chunks and a `Barrier(4)` proving `concurrency=4` reaches four simultaneous provider calls without exceeding four.
- [x] Add a failing test proving `concurrency=1` retains the current serial behavior.
- [x] Add a failing deterministic-order test: deliberately complete chunks in reverse order, then assert imported/merged entities remain in source order (`甲`, `乙`, `丙`).
- [x] Run the focused tests and confirm the expected failures.

```bash
.venv/bin/python -m pytest -q apps/api/tests/extraction/test_pipeline.py -k 'concurrency or source_order'
```

- [x] Add a private outcome value that carries source index, chunk, result, retry count, and optional skip code.

```python
@dataclass(frozen=True)
class ChunkExtractionOutcome:
    index: int
    chunk: TextChunk
    extracted: ExtractionResult | None
    retries: int = 0
    error_code: str | None = None
```

- [x] Extend `ExtractionPipeline.__init__` with `concurrency: int = 1` and reject values outside `1–16` defensively.
- [x] Extract one chunk in `_extract_chunk`; keep `_extract_with_retries` unchanged and convert only `MODEL_CONTENT_FILTER` into a skipped outcome. Let other provider errors propagate.
- [x] Implement `_extract_chunks` with `ThreadPoolExecutor`, a `future -> (index, chunk)` map, and a sliding window no larger than `self.concurrency`.
- [x] Use `wait(..., return_when=FIRST_COMPLETED)` so each completion advances persisted progress and opens one new submission slot.
- [x] Check cancellation before initial submission, before every refill, and after each completed future. On abort, cancel pending futures and call `shutdown(wait=True, cancel_futures=True)`.
- [x] Sort successful/skipped outcomes by source index before the existing normalization and merge logic runs.
- [x] Keep progress counting based on completed provider calls, while preserving the visible “current chunk / total chunks” contract.
- [x] Keep the final cancellation check immediately before the single Neo4j import.
- [x] Wire the setting into the worker composition root.

```python
pipeline = ExtractionPipeline(
    GraphImporter(graph),
    concurrency=settings.extraction_concurrency,
)
```

- [x] Run all extraction pipeline tests.

```bash
.venv/bin/python -m pytest -q apps/api/tests/extraction/test_pipeline.py
```

- [x] Commit the bounded-success-path implementation.

```bash
git add apps/api/src/app/extraction/pipeline.py apps/api/src/app/worker/main.py apps/api/tests/extraction/test_pipeline.py
git commit -m "perf: run extraction requests with bounded concurrency"
```

## Task 3: Make retries, cancellation, and fatal errors concurrency-safe

**Files:**

- Modify: `apps/api/src/app/extraction/pipeline.py`
- Modify: `apps/api/tests/extraction/test_pipeline.py`

- [x] Add a retry-isolation test: one chunk fails transiently and sleeps before retry, while another chunk completes during that backoff. Assert the second chunk is not blocked by the first chunk's retry delay.
- [x] Add a cancellation test with four chunks and `concurrency=2`: let exactly two calls enter through `Barrier(2)`, trigger cancellation, and assert no third call starts, no entities/facts are written, and the importer is never called.
- [x] Add a fatal-error test with `坏`, `在途`, and `未提交`: run the first two concurrently, make `坏` raise `INVALID_RESPONSE`, allow `在途` to finish, and assert `未提交` never starts and no import occurs.
- [x] Assert fatal logs include the exact failing chunk ID and provider error code, but never source text, prompts, or credentials.
- [x] Run these new tests and confirm they fail before the safety implementation.

```bash
.venv/bin/python -m pytest -q apps/api/tests/extraction/test_pipeline.py -k 'retry_isolation or concurrent_cancel or concurrent_fatal'
```

- [x] Keep the future-to-chunk mapping available until `future.result()` succeeds or raises so failure logs identify the correct chunk.
- [x] On the first fatal exception, stop refilling the window, cancel all not-yet-running futures, wait for running futures, discard every result, and re-raise the original provider error.
- [x] On cancellation, use the same drain path but raise the existing cancellation signal rather than a provider error.
- [x] Emit one structured batch-start log, one cancellation/fatal summary, and retain the existing per-request timing logs. Do not log full request or response bodies.
- [x] Confirm content-filter handling remains a per-chunk skip and does not abort other chunks.
- [x] Run the safety tests repeatedly to catch race-sensitive failures.

```bash
.venv/bin/python -m pytest -q apps/api/tests/extraction/test_pipeline.py -k 'retry_isolation or concurrent_cancel or concurrent_fatal'
.venv/bin/python -m pytest -q apps/api/tests/extraction/test_pipeline.py -k 'retry_isolation or concurrent_cancel or concurrent_fatal'
.venv/bin/python -m pytest -q apps/api/tests/extraction/test_pipeline.py -k 'retry_isolation or concurrent_cancel or concurrent_fatal'
.venv/bin/python -m pytest -q apps/api/tests/extraction/test_pipeline.py -k 'retry_isolation or concurrent_cancel or concurrent_fatal'
.venv/bin/python -m pytest -q apps/api/tests/extraction/test_pipeline.py -k 'retry_isolation or concurrent_cancel or concurrent_fatal'
```

- [x] Run the complete pipeline suite and commit.

```bash
.venv/bin/python -m pytest -q apps/api/tests/extraction/test_pipeline.py
git add apps/api/src/app/extraction/pipeline.py apps/api/tests/extraction/test_pipeline.py
git commit -m "fix: make concurrent extraction cancellation safe"
```

## Task 4: Cover attribute backfill, document rollout, and run final gates

**Files:**

- Modify: `apps/api/tests/extraction/test_pipeline.py`
- Modify: `docs/deployment-docker-azure-openai.md`
- Verify: `apps/api/src/app/worker/online.py`

- [x] Add an attribute-only pipeline test using two source chunks and `Barrier(2)`, asserting configured concurrency is used and only attribute data—not entities or relationships—is imported.
- [x] Confirm both full-build and attribute-backfill handlers in `worker/online.py` use the same configured pipeline instance; do not duplicate executor logic in job handlers.
- [x] Run the attribute and full-build tests.

```bash
.venv/bin/python -m pytest -q apps/api/tests/extraction/test_pipeline.py -k 'attribute or concurrency'
```

- [x] Document server configuration and rollout.

```dotenv
EXTRACTION_CONCURRENCY=4
```

```bash
sudo docker compose config
sudo docker compose up -d --build worker
sudo docker compose exec worker printenv EXTRACTION_CONCURRENCY
sudo docker compose logs -f worker
```

- [x] Document that `1` restores serial execution, `2` is the conservative fallback, cancellation cannot interrupt an already-running synchronous HTTP call, and higher concurrency consumes RPM/TPM quota faster.
- [x] Run the API suite, excluding the repository's opt-in live Neo4j test.

```bash
.venv/bin/python -m pytest -q apps/api/tests -k 'not test_review_scan_and_items_endpoint'
```

- [x] Run syntax, Compose, and patch hygiene checks.

```bash
.venv/bin/python -m compileall -q apps/api/src
docker compose config >/dev/null
git diff --check
git status --short
```

- [x] Review the final diff for the following invariants:

  - No secrets, source text, prompt bodies, or full model responses are logged.
  - Provider public interfaces and extraction schemas remain backward compatible.
  - SQLite/Neo4j writes remain on the main worker thread.
  - A failed or cancelled batch cannot publish a partial graph.
  - Default concurrency remains `1`.
  - Full builds and attribute backfills both honor the same setting.

- [x] Commit documentation and final coverage.

```bash
git add apps/api/tests/extraction/test_pipeline.py docs/deployment-docker-azure-openai.md
git commit -m "docs: document concurrent extraction rollout"
```

## Completion Criteria

- [x] `EXTRACTION_CONCURRENCY=1` is behaviorally equivalent to the current serial implementation.
- [x] A configured value of `N` never produces more than `N` simultaneous model requests in one worker process.
- [x] Completion order cannot change the graph's deterministic source-order merge.
- [x] Retries occupy only their own slot and do not block other active slots.
- [x] Cancellation and fatal errors stop new submissions and prevent import.
- [x] Progress advances on each completed or deliberately skipped chunk.
- [x] Deployment documentation includes validation, observability, tuning, and rollback steps.
