# Build Progress and Operation Lock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist and stream real chunk progress while preventing conflicting Build-page operations until the active job completes or is cancelled.

**Architecture:** `JobRepository` becomes the source of truth for active-job exclusion and monotonic progress. `ExtractionPipeline` reports chunk boundaries through callbacks, while `OnlineBuildHandlers` connects those callbacks to SQLite and `WorkerRunner` protects terminal states from stale transitions. React derives one `processing` flag from the current snapshot, publishes a project-switch lock through `ProjectContext`, disables mutation controls, and renders determinate or indeterminate progress from the persisted counters.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, SQLite, pytest, React 19, TypeScript, React Router, Vitest, Testing Library, SSE.

## Global Constraints

- A non-terminal job locks Build upload controls, attribute-backfill controls, and the current-project selector.
- Top navigation remains available; the active job's Cancel action remains available until final graph import begins.
- Pause/Resume remain API-compatible but are removed from the Build UI because safe checkpoint resume is out of scope.
- `completed_chunks` is monotonic, never exceeds `total_chunks`, and includes explicitly skipped content-filtered chunks.
- No partial graph is imported after cancellation.
- Existing `jobs` columns and `JobSnapshot` response fields remain backward-compatible; no database migration is introduced.
- SSE remains the primary update channel and two-second polling remains the fallback.
- All behavior changes are test-driven and committed as small, reviewable increments.

---

## File Map

- `apps/api/src/app/jobs/repository.py`: atomic job creation, progress invariants, event persistence, active-job lookup.
- `apps/api/src/app/jobs/service.py`: cancellation boundary rules.
- `apps/api/src/app/jobs/models.py`: allow cancellation from the currently overloaded `IMPORTING` state.
- `apps/api/src/app/extraction/pipeline.py`: progress/cancellation callback contract and chunk-boundary checks.
- `apps/api/src/app/worker/online.py`: bind Pipeline callbacks to the job repository.
- `apps/api/src/app/worker/runner.py`: do not overwrite a terminal state after a long-running handler returns.
- `apps/api/src/app/projects/router.py`: translate active-job conflict into HTTP 409.
- `apps/web/src/app/ProjectContext.tsx`: expose a scoped project-switch lock.
- `apps/web/src/features/projects/ProjectSwitcher.tsx`: disable project switching while locked.
- `apps/web/src/features/build/BuildPage.tsx`: derive and publish the processing state.
- `apps/web/src/features/build/UploadStep.tsx`: disable the complete upload form.
- `apps/web/src/features/build/AttributeBackfill.tsx`: disable attribute-backfill mutations.
- `apps/web/src/features/build/JobProgress.tsx`: truthful stage copy, cancel boundary, determinate/indeterminate progress.
- `apps/web/src/styles/vercel.css`: locked-panel and indeterminate-progress presentation.

---

### Task 1: Enforce Active-Job and Progress Invariants in SQLite

**Files:**
- Modify: `apps/api/src/app/jobs/repository.py`
- Modify: `apps/api/src/app/jobs/models.py`
- Modify: `apps/api/src/app/jobs/service.py`
- Test: `apps/api/tests/jobs/test_repository.py`
- Test: `apps/api/tests/jobs/test_router.py`

**Interfaces:**
- Produces: `ProjectJobInProgressError(project_id: str)`.
- Produces: `JobRepository.update_progress(job_id: str, completed_chunks: int, total_chunks: int) -> bool`.
- Produces: `JobRepository.has_active_job(project_id: str) -> bool`.
- `update_progress()` returns `False` without writing an event when the job is already terminal.

- [ ] **Step 1: Write failing repository tests for active-job exclusion**

Append tests that prove one project cannot have two non-terminal jobs, while a completed job permits a new one:

```python
from app.jobs.repository import JobRepository, ProjectJobInProgressError


def test_create_rejects_a_second_active_job_for_the_same_project():
    repository = JobRepository(create_engine("sqlite+pysqlite:///:memory:"))
    repository.create("p-1", "fixed:test")

    with pytest.raises(ProjectJobInProgressError, match="p-1"):
        repository.create("p-1", "fixed:test", JobKind.ATTRIBUTE_BACKFILL)

    repository.create("p-2", "fixed:test")


def test_create_allows_a_new_job_after_the_previous_job_is_terminal():
    repository = JobRepository(create_engine("sqlite+pysqlite:///:memory:"))
    first = repository.create("p-1", "fixed:test")
    repository.set_status(first.id, JobStatus.COMPLETED)

    second = repository.create("p-1", "fixed:test")

    assert second.id != first.id
```

- [ ] **Step 2: Write failing repository tests for monotonic progress and events**

```python
def test_update_progress_is_monotonic_and_emits_snapshots():
    repository = JobRepository(create_engine("sqlite+pysqlite:///:memory:"))
    job = repository.create("p-1", "fixed:test")

    assert repository.update_progress(job.id, 0, 3) is True
    assert repository.update_progress(job.id, 1, 3) is True
    updated = repository.get_required(job.id)

    assert (updated.completed_chunks, updated.total_chunks) == (1, 3)
    assert repository.events_after(job.id, 0)[-1].snapshot["completed_chunks"] == 1


@pytest.mark.parametrize("completed,total", [(2, 1), (-1, 1), (0, -1)])
def test_update_progress_rejects_invalid_bounds(completed, total):
    repository = JobRepository(create_engine("sqlite+pysqlite:///:memory:"))
    job = repository.create("p-1", "fixed:test")

    with pytest.raises(ValueError, match="INVALID_JOB_PROGRESS"):
        repository.update_progress(job.id, completed, total)


def test_update_progress_rejects_regression_and_ignores_terminal_jobs():
    repository = JobRepository(create_engine("sqlite+pysqlite:///:memory:"))
    job = repository.create("p-1", "fixed:test")
    repository.update_progress(job.id, 2, 3)

    with pytest.raises(ValueError, match="JOB_PROGRESS_REGRESSION"):
        repository.update_progress(job.id, 1, 3)

    repository.set_status(job.id, JobStatus.CANCELLED)
    assert repository.update_progress(job.id, 3, 3) is False
    assert repository.get_required(job.id).completed_chunks == 2
```

- [ ] **Step 3: Run the focused repository tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/jobs/test_repository.py -v
```

Expected: FAIL because `ProjectJobInProgressError` and `update_progress` do not exist and `create()` permits duplicate active jobs.

- [ ] **Step 4: Implement atomic creation and progress persistence**

Add the error and use the existing SQLite write-lock pattern:

```python
class ProjectJobInProgressError(RuntimeError):
    pass


def create(self, project_id: str, model_profile_id: str,
           kind: JobKind = JobKind.FULL_BUILD) -> Job:
    with Session(self.engine) as session:
        if self.engine.dialect.name == "sqlite":
            session.execute(text("BEGIN IMMEDIATE"))
        active = session.scalar(
            select(Job.id).where(
                Job.project_id == project_id,
                Job.status.not_in(
                    [status.value for status in TERMINAL_STATUSES]
                ),
            ).limit(1)
        )
        if active is not None:
            session.rollback()
            raise ProjectJobInProgressError(project_id)
        job = Job(
            project_id=project_id,
            model_profile_id=model_profile_id,
            kind=kind,
        )
        session.add(job)
        session.commit()
        job_id = job.id
    self._append_event(job_id)
    return self.get_required(job_id)
```

Add a progress update that validates and writes the Job Event only after commit:

```python
def update_progress(
    self, job_id: str, completed_chunks: int, total_chunks: int
) -> bool:
    if completed_chunks < 0 or total_chunks < 0 or completed_chunks > total_chunks:
        raise ValueError("INVALID_JOB_PROGRESS")
    with Session(self.engine) as session:
        if self.engine.dialect.name == "sqlite":
            session.execute(text("BEGIN IMMEDIATE"))
        job = session.get(Job, job_id)
        if job is None:
            raise LookupError(job_id)
        if JobStatus(job.status) in TERMINAL_STATUSES:
            session.rollback()
            return False
        if (
            completed_chunks < job.completed_chunks
            or total_chunks < job.total_chunks
        ):
            raise ValueError("JOB_PROGRESS_REGRESSION")
        job.completed_chunks = completed_chunks
        job.total_chunks = total_chunks
        job.updated_at = self.clock()
        session.commit()
    self._append_event(job_id)
    return True
```

Implement `has_active_job()` with the same terminal-status predicate for router/service use.

- [ ] **Step 5: Tighten cancellation at final import**

Add `JobStatus.CANCELLED` to the model's `IMPORTING` transition set, then enforce the finer boundary in `JobService.cancel()`:

```python
def cancel(self, job_id: str) -> Job:
    job = self.get(job_id)
    if (
        JobStatus(job.status) == JobStatus.IMPORTING
        and job.total_chunks > 0
        and job.completed_chunks >= job.total_chunks
    ):
        raise InvalidJobTransition(f"{job.status}->{JobStatus.CANCELLED}")
    return self.repository.set_status(
        job_id, transition(job.status, JobStatus.CANCELLED)
    )
```

Add router tests:

```python
def test_cancel_is_allowed_during_chunk_processing():
    client, repository = make_client()
    job = repository.create("p-1", "fixed:test")
    repository.set_status(job.id, JobStatus.IMPORTING)
    repository.update_progress(job.id, 1, 3)

    assert client.post(f"/api/jobs/{job.id}/cancel").json()["status"] == "CANCELLED"


def test_cancel_is_rejected_after_all_chunks_finish():
    client, repository = make_client()
    job = repository.create("p-1", "fixed:test")
    repository.set_status(job.id, JobStatus.IMPORTING)
    repository.update_progress(job.id, 3, 3)

    response = client.post(f"/api/jobs/{job.id}/cancel")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "INVALID_JOB_TRANSITION"
```

- [ ] **Step 6: Run job tests**

Run:

```bash
.venv/bin/python -m pytest \
  apps/api/tests/jobs/test_repository.py \
  apps/api/tests/jobs/test_router.py -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/app/jobs apps/api/tests/jobs
git commit -m "feat: enforce job progress invariants"
```

---

### Task 2: Report Real Chunk Progress from the Extraction Pipeline

**Files:**
- Modify: `apps/api/src/app/extraction/pipeline.py`
- Test: `apps/api/tests/extraction/test_pipeline.py`

**Interfaces:**
- Produces: `PipelineCancelled(RuntimeError)`.
- Extends: `ExtractionPipeline.process(..., on_progress: Callable[[int, int], None] | None = None, should_cancel: Callable[[], bool] | None = None) -> PipelineResult`.
- Does not change callers that omit the new keyword arguments.

- [ ] **Step 1: Write failing tests for initial and incremental callbacks**

Use a source that splits into two chunks and assert the exact monotonic sequence:

```python
def test_pipeline_reports_total_and_each_completed_chunk(monkeypatch):
    chunks = [
        SimpleNamespace(id="c-1", text="甲识乙"),
        SimpleNamespace(id="c-2", text="丙识丁"),
    ]
    split = SimpleNamespace(chunks=chunks, chapters=[])
    monkeypatch.setattr("app.extraction.pipeline.split_document", lambda _: split)
    progress = []

    ExtractionPipeline(GraphImporter(MemoryWriter())).process(
        "p-1", "测试", "source", EmptyProvider(),
        on_progress=lambda completed, total: progress.append((completed, total)),
    )

    assert progress == [(0, 2), (1, 2), (2, 2)]
```

Add a content-filter test asserting it still reports `(1, 1)`.

- [ ] **Step 2: Write a failing cancellation test**

```python
def test_pipeline_stops_before_import_when_cancelled(monkeypatch):
    provider = EmptyProvider()
    writer = CapturingWriter()
    checks = iter([False, False, True])

    with pytest.raises(PipelineCancelled):
        ExtractionPipeline(GraphImporter(writer)).process(
            "p-1", "测试", "第一章\n甲识乙",
            provider,
            should_cancel=lambda: next(checks, True),
        )

    assert writer.rows == {"Entity": [], "Fact": [], "Evidence": []}
```

Structure the check sequence so cancellation occurs after a processed chunk but before `import_document()`.

- [ ] **Step 3: Run the pipeline tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/extraction/test_pipeline.py -v
```

Expected: FAIL because `process()` does not accept callbacks and `PipelineCancelled` is undefined.

- [ ] **Step 4: Implement callback defaults and checkpoints**

Add:

```python
class PipelineCancelled(RuntimeError):
    pass


def _never_cancel() -> bool:
    return False


def _ignore_progress(completed: int, total: int) -> None:
    return None
```

Extend `process()` and call the hooks in this order:

```python
cancelled = should_cancel or _never_cancel
progress = on_progress or _ignore_progress
split = split_document(source)
total_chunks = len(split.chunks)
progress(0, total_chunks)

for index, chunk in enumerate(split.chunks, start=1):
    if cancelled():
        raise PipelineCancelled("JOB_CANCELLED")
    # existing provider, rule and normalization logic
    progress(index, total_chunks)
    if cancelled():
        raise PipelineCancelled("JOB_CANCELLED")

if cancelled():
    raise PipelineCancelled("JOB_CANCELLED")
# existing GraphDocument construction and importer call
```

For the content-filter `continue` branch, call `progress(index, total_chunks)` before continuing.

- [ ] **Step 5: Run all extraction tests**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/extraction -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/app/extraction/pipeline.py apps/api/tests/extraction/test_pipeline.py
git commit -m "feat: report extraction chunk progress"
```

---

### Task 3: Bind Worker Progress and Preserve Terminal States

**Files:**
- Modify: `apps/api/src/app/worker/online.py`
- Modify: `apps/api/src/app/worker/runner.py`
- Test: `apps/api/tests/worker/test_runner.py`

**Interfaces:**
- Consumes: `JobRepository.update_progress(...) -> bool`.
- Consumes: `PipelineCancelled`.
- Produces: stale Worker handlers cannot replace `CANCELLED`, `FAILED`, or `COMPLETED`.

- [ ] **Step 1: Write a failing Runner test for cancellation races**

```python
def test_runner_does_not_overwrite_terminal_status_set_inside_handler():
    repository = JobRepository(create_engine("sqlite+pysqlite:///:memory:"))
    job = repository.create("p-1", "fixed:test")

    def cancel_during_stage(claimed):
        repository.set_status(claimed.id, JobStatus.CANCELLED)

    runner = WorkerRunner(
        repository,
        worker_id="w-1",
        handlers={JobStatus.SPLITTING: cancel_during_stage},
    )

    runner.run_once()

    assert repository.get_required(job.id).status == JobStatus.CANCELLED
```

- [ ] **Step 2: Write a failing online-handler progress test**

Extend `test_online_handlers_complete_fixed_provider_job()` to assert:

```python
completed = jobs.get_required(job.id)
assert completed.completed_chunks == 1
assert completed.total_chunks == 1
assert any(
    event.snapshot["total_chunks"] == 1
    for event in jobs.events_after(job.id, 0)
)
```

Add a Pipeline test double that calls `on_progress(0, 2)`, `on_progress(1, 2)`, changes the repository to `CANCELLED`, then raises `PipelineCancelled`. Assert the Worker leaves the job cancelled and does not save quality.

- [ ] **Step 3: Run Worker tests and verify failure**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/worker/test_runner.py -v
```

Expected: FAIL because Runner advances stale state and `_build()` does not pass callbacks.

- [ ] **Step 4: Wire repository callbacks in `OnlineBuildHandlers`**

Use closures bound to `job.id`:

```python
def on_progress(completed: int, total: int) -> None:
    if not self.jobs.update_progress(job.id, completed, total):
        raise PipelineCancelled("JOB_CANCELLED")

def should_cancel() -> bool:
    current = self.jobs.get_required(job.id)
    return JobStatus(current.status) == JobStatus.CANCELLED

try:
    result = self.pipeline.process(
        project.id,
        project.title,
        source,
        self.providers.create(job.model_profile_id),
        attributes_only=attributes_only,
        on_progress=on_progress,
        should_cancel=should_cancel,
    )
except PipelineCancelled:
    return
```

Save quality only after a non-cancelled Pipeline result.

- [ ] **Step 5: Re-read status in `WorkerRunner` before every terminal write**

After `handler(job)`:

```python
current = self.repository.get_required(job.id)
if JobStatus(current.status) in TERMINAL_STATUSES:
    return True
self.repository.set_status(job.id, NEXT_STATUS[job.status])
```

Apply the same guard in exception handlers so a cancellation race does not become `FAILED`.

- [ ] **Step 6: Run Worker and job tests**

Run:

```bash
.venv/bin/python -m pytest \
  apps/api/tests/worker \
  apps/api/tests/jobs -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/app/worker apps/api/tests/worker
git commit -m "fix: preserve worker cancellation state"
```

---

### Task 4: Return a Stable 409 for Conflicting Project Jobs

**Files:**
- Modify: `apps/api/src/app/projects/router.py`
- Test: `apps/api/tests/jobs/test_attribute_jobs.py`
- Test: `apps/api/tests/projects/test_router.py`

**Interfaces:**
- Consumes: `ProjectJobInProgressError`.
- Produces: HTTP `409` with `{"detail": {"code": "PROJECT_JOB_IN_PROGRESS"}}`.

- [ ] **Step 1: Write the failing attribute-job conflict test**

```python
def test_attribute_job_rejects_when_project_already_has_an_active_job(tmp_path):
    client, projects, jobs, _ = make_client(tmp_path)
    user_project = next(
        project for project in projects.list_projects()
        if not project.is_builtin
    )
    jobs.create(user_project.id, "fixed:test")

    response = client.post(
        f"/api/projects/{user_project.id}/attribute-jobs",
        json={"model_profile_id": "fixed:test"},
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": {"code": "PROJECT_JOB_IN_PROGRESS"}
    }
```

- [ ] **Step 2: Run the focused API test and verify failure**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests/jobs/test_attribute_jobs.py -v
```

Expected: FAIL because the repository exception is not translated to HTTP 409.

- [ ] **Step 3: Add one router helper and use it in both creation paths**

```python
def create_job_or_conflict(jobs: JobRepository, *args, **kwargs):
    try:
        return jobs.create(*args, **kwargs)
    except ProjectJobInProgressError as error:
        raise HTTPException(
            status_code=409,
            detail={"code": "PROJECT_JOB_IN_PROGRESS"},
        ) from error
```

Use the helper for upload-created full jobs and attribute-backfill jobs. Preserve the existing upload cleanup block when any exception occurs.

- [ ] **Step 4: Run project/job router tests**

Run:

```bash
.venv/bin/python -m pytest \
  apps/api/tests/jobs/test_attribute_jobs.py \
  apps/api/tests/projects -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/app/projects/router.py apps/api/tests/jobs apps/api/tests/projects
git commit -m "fix: reject concurrent project jobs"
```

---

### Task 5: Publish a Build Operation Lock to the Project Switcher

**Files:**
- Modify: `apps/web/src/app/ProjectContext.tsx`
- Modify: `apps/web/src/app/ProjectContext.test.tsx`
- Modify: `apps/web/src/features/projects/ProjectSwitcher.tsx`
- Modify: `apps/web/src/features/build/BuildPage.tsx`
- Modify: `apps/web/src/features/build/UploadStep.tsx`
- Modify: `apps/web/src/features/build/AttributeBackfill.tsx`
- Test: `apps/web/src/features/build/BuildPage.test.tsx`

**Interfaces:**
- Produces from `useProject()`: `projectSwitchLocked: boolean`.
- Produces from `useProject()`: `setProjectSwitchLocked(locked: boolean): void`.
- Adds to Build child components: `disabled: boolean`.

- [ ] **Step 1: Write failing Build tests for locked mutations**

Restore a URL job with status `IMPORTING`, `completed_chunks: 1`, `total_chunks: 3`, then assert:

```tsx
expect(await screen.findByText('抽取实体、关系与属性')).toBeVisible()
expect(screen.getByLabelText('项目标题')).toBeDisabled()
expect(screen.getByLabelText('TXT 小说')).toBeDisabled()
expect(screen.getByLabelText('模型配置')).toBeDisabled()
expect(screen.getByRole('button', { name: '开始构建' })).toBeDisabled()
expect(screen.getByLabelText('属性补抽模型')).toBeDisabled()
expect(screen.getByRole('button', { name: '重新抽取属性' })).toBeDisabled()
expect(screen.getByLabelText('当前项目')).toBeDisabled()
expect(screen.queryByRole('button', { name: '暂停' })).not.toBeInTheDocument()
expect(screen.getByRole('button', { name: '取消' })).toBeEnabled()
```

Render `ProjectSwitcher` beside `BuildPage` within the same `ProjectProvider` so the test exercises the real shared context.

- [ ] **Step 2: Write a failing test that terminal jobs unlock controls**

Use an EventSource test double capable of emitting a `job` event. Emit:

```json
{
  "id": "job-1",
  "project_id": "project-1",
  "model_profile_id": "fixed:test",
  "kind": "FULL_BUILD",
  "status": "COMPLETED",
  "completed_chunks": 3,
  "total_chunks": 3
}
```

Assert the upload controls and project selector become enabled after the event.

- [ ] **Step 3: Run the focused web tests and verify failure**

Run:

```bash
npm --prefix apps/web test -- --run \
  src/features/build/BuildPage.test.tsx \
  src/app/ProjectContext.test.tsx
```

Expected: FAIL because no shared switch lock or child `disabled` props exist.

- [ ] **Step 4: Add the scoped lock to `ProjectContext`**

Extend the context:

```tsx
type ProjectContextValue = {
  projects: ProjectSummary[]
  projectId: string
  setProjectId: (id: string) => void
  refreshProjects: () => Promise<void>
  projectSwitchLocked: boolean
  setProjectSwitchLocked: (locked: boolean) => void
}
```

Keep `setProjectId()` unchanged for programmatic navigation. Only `ProjectSwitcher` consumes `projectSwitchLocked`:

```tsx
const { projects, projectId, setProjectId, projectSwitchLocked } = useProject()
<select
  aria-label="当前项目"
  value={projectId}
  disabled={projectSwitchLocked}
  onChange={event => setProjectId(event.target.value)}
>
```

- [ ] **Step 5: Derive and publish processing state in `BuildPage`**

```tsx
const terminal = new Set(['COMPLETED', 'FAILED', 'CANCELLED'])
const processing = Boolean(created && !terminal.has(created.job.status))
const { setProjectSwitchLocked } = useProject()

useEffect(() => {
  setProjectSwitchLocked(processing)
  return () => setProjectSwitchLocked(false)
}, [processing, setProjectSwitchLocked])
```

Pass `disabled={processing}` to `UploadStep` and `AttributeBackfill`. Render the lock explanation only while processing.

- [ ] **Step 6: Disable every mutation control**

In `UploadStep`, apply `disabled={disabled}` to title, file and model fields, and use:

```tsx
disabled={busy || disabled || !profile}
```

In `AttributeBackfill`, disable the model selector and use:

```tsx
disabled={busy || disabled || !profile || !sourceAvailable}
```

- [ ] **Step 7: Run focused web tests**

Run:

```bash
npm --prefix apps/web test -- --run \
  src/features/build/BuildPage.test.tsx \
  src/app/ProjectContext.test.tsx
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add apps/web/src/app apps/web/src/features/build apps/web/src/features/projects
git commit -m "fix: lock build mutations during processing"
```

---

### Task 6: Render Truthful Determinate and Indeterminate Progress

**Files:**
- Modify: `apps/web/src/features/build/JobProgress.tsx`
- Modify: `apps/web/src/features/build/BuildPage.test.tsx`
- Modify: `apps/web/src/styles/vercel.css`

**Interfaces:**
- Consumes: real `completed_chunks` and `total_chunks`.
- Produces: no `value` attribute for indeterminate progress.
- Produces: `value="33"` and “已完成 1 / 总计 3 个片段” for determinate progress.

- [ ] **Step 1: Add failing presentation tests**

Test three snapshots:

```tsx
// Before split
expect(screen.getByRole('progressbar', { name: '构建进度' }))
  .not.toHaveAttribute('value')
expect(screen.getByText('正在分析文本结构')).toBeVisible()

// During chunks
expect(screen.getByRole('progressbar', { name: '构建进度' }))
  .toHaveAttribute('value', '33')
expect(screen.getByText('已完成 1 / 总计 3 个片段')).toBeVisible()

// All chunks processed but not terminal
expect(screen.getByRole('progressbar', { name: '构建进度' }))
  .not.toHaveAttribute('value')
expect(screen.getByText('正在汇总并写入 Neo4j')).toBeVisible()
expect(screen.getByRole('button', { name: '取消' })).toBeDisabled()
```

Add a completed snapshot test expecting `value="100"` and “已完成 3 / 总计 3 个片段”.

- [ ] **Step 2: Run the presentation tests and verify failure**

Run:

```bash
npm --prefix apps/web test -- --run src/features/build/BuildPage.test.tsx
```

Expected: FAIL because the current component always renders `value=0`, uses raw status copy, and exposes Pause.

- [ ] **Step 3: Implement a progress-view helper**

Inside `JobProgress.tsx`, derive:

```tsx
function progressView(job: JobSnapshot) {
  if (job.status === 'COMPLETED') {
    return { label: '构建完成', value: 100, detail: `已完成 ${job.total_chunks} / 总计 ${job.total_chunks} 个片段` }
  }
  if (job.total_chunks === 0) {
    return { label: '正在分析文本结构', detail: '正在识别章节并切分文本' }
  }
  if (job.completed_chunks < job.total_chunks) {
    return {
      label: job.kind === 'ATTRIBUTE_BACKFILL'
        ? '补抽实体属性'
        : '抽取实体、关系与属性',
      value: Math.round(job.completed_chunks / job.total_chunks * 100),
      detail: `已完成 ${job.completed_chunks} / 总计 ${job.total_chunks} 个片段`,
    }
  }
  return {
    label: '正在汇总并写入 Neo4j',
    detail: `已完成 ${job.completed_chunks} / 总计 ${job.total_chunks} 个片段`,
  }
}
```

For `FAILED` and `CANCELLED`, preserve the last calculable numeric value instead of returning an active-stage label.

Render:

```tsx
<progress
  aria-label="构建进度"
  max="100"
  {...(view.value === undefined ? {} : { value: view.value })}
/>
```

Remove Pause/Resume buttons. Disable Cancel when all known chunks are complete.

- [ ] **Step 4: Add locked and indeterminate styles**

Add:

```css
.build-source-stack[aria-disabled="true"] {
  background: var(--ds-background-recessed);
}

.build-lock-note {
  margin: 0 24px 24px;
  color: var(--ds-text-secondary);
  font-size: 12px;
}

.job-progress-bar {
  position: relative;
  overflow: hidden;
  height: 8px;
  border-radius: 9999px;
  background: var(--ds-background-recessed);
}

.job-progress-bar > progress {
  display: block;
  width: 100%;
  height: 8px;
}

.job-progress-indicator {
  position: absolute;
  inset: 0 auto 0 0;
  width: 25%;
  border-radius: inherit;
  background: var(--ds-text-primary);
  animation: build-progress-indeterminate 1.4s ease-in-out infinite;
}

@keyframes build-progress-indeterminate {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(300%); }
}

@media (prefers-reduced-motion: reduce) {
  .job-progress-indicator {
    animation: none;
    left: 37.5%;
  }
}
```

Wrap the native element so the animated indicator is browser-independent:

```tsx
<div className="job-progress-bar">
  <progress
    aria-label="构建进度"
    max="100"
    {...(view.value === undefined ? {} : { value: view.value })}
  />
  {view.value === undefined && (
    <span className="job-progress-indicator" aria-hidden="true" />
  )}
</div>
```

- [ ] **Step 5: Run web tests, typecheck and build**

Run:

```bash
npm --prefix apps/web test -- --run
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

Expected: all commands PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/features/build apps/web/src/styles/vercel.css
git commit -m "feat: show truthful build progress"
```

---

### Task 7: Full Verification and Browser Acceptance

**Files:**
- Modify only if verification exposes a defect in the files already listed.

**Interfaces:**
- Verifies the complete API → SQLite event → SSE/polling → React progress path.

- [ ] **Step 1: Run the full automated suite**

Run:

```bash
.venv/bin/python -m pytest apps/api/tests -v
npm --prefix apps/web test -- --run
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
```

Expected: all commands PASS with zero failures.

- [ ] **Step 2: Start the local Docker application**

Run:

```bash
docker compose up -d --build --wait --wait-timeout 120
```

Expected: `api`, `worker`, `web`, and `neo4j` are healthy/running.

- [ ] **Step 3: Verify the operation lock in a real browser**

Using an administrator session:

1. Open `/build`.
2. Upload a multi-chunk TXT with `fixed:test` or an available non-production test profile.
3. Confirm title, file, model, Start Build, attribute model, attribute action, and project selector are disabled immediately.
4. Confirm main navigation links remain operable.
5. Confirm no Pause button is present.

Expected: only Cancel and read-only navigation remain actionable while chunks are processing.

- [ ] **Step 4: Verify live progress and cancellation**

Observe Network and UI:

1. Confirm `/api/jobs/{id}/events` delivers snapshots where `total_chunks > 0`.
2. Confirm `completed_chunks` increases monotonically.
3. Confirm the UI changes from indeterminate to numeric progress.
4. Cancel before the final chunk and confirm the status remains `CANCELLED`.
5. Confirm no quality report or partial graph is created for the cancelled job.

Expected: visible progress advances without a manual refresh, and cancellation is not overwritten by Worker completion.

- [ ] **Step 5: Verify backend duplicate protection**

While a project job is active, submit a second attribute-job request using the authenticated browser/API session.

Expected:

```json
HTTP 409
{"detail":{"code":"PROJECT_JOB_IN_PROGRESS"}}
```

- [ ] **Step 6: Review the final diff and commit any verification-only correction**

Run:

```bash
git diff --check
git status --short
git log --oneline origin/master..HEAD
```

Expected: clean diff checks and only scoped commits. If browser verification required a correction, test it and commit:

```bash
git add \
  apps/api/src/app/jobs \
  apps/api/src/app/extraction/pipeline.py \
  apps/api/src/app/worker \
  apps/api/src/app/projects/router.py \
  apps/api/tests \
  apps/web/src/app \
  apps/web/src/features/build \
  apps/web/src/features/projects \
  apps/web/src/styles/vercel.css
git commit -m "fix: address build progress acceptance findings"
```
