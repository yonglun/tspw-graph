from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier, Lock

import pytest
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.exc import OperationalError

from app.jobs.models import InvalidJobTransition, JobKind, JobStatus, transition
from app.jobs.repository import JobRepository, ProjectJobInProgressError


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, *, seconds: int) -> None:
        self.now += timedelta(seconds=seconds)


def test_illegal_transition_is_rejected():
    with pytest.raises(InvalidJobTransition):
        transition(JobStatus.COMPLETED, JobStatus.EXTRACTING)


def test_expired_lease_can_be_reclaimed():
    clock = Clock()
    repository = JobRepository(
        create_engine("sqlite+pysqlite:///:memory:"), clock=clock
    )
    job = repository.create("p-1", "fixed:test")

    assert repository.claim_next("w-1", 30).id == job.id
    assert repository.claim_next("w-2", 30) is None
    clock.advance(seconds=31)
    assert repository.claim_next("w-2", 30).id == job.id


def test_events_are_monotonic_and_filterable():
    repository = JobRepository(create_engine("sqlite+pysqlite:///:memory:"))
    job = repository.create("p-1", "fixed:test")
    repository.set_status(job.id, JobStatus.PAUSED)

    events = repository.events_after(job.id, 1)

    assert [event.sequence for event in events] == [2]
    assert events[0].snapshot["status"] == "PAUSED"


def test_legacy_sqlite_jobs_table_is_upgraded_with_full_build_default():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("PRAGMA foreign_keys=ON"))
        connection.execute(
            text(
                """
                CREATE TABLE projects (
                    id VARCHAR(100) PRIMARY KEY,
                    title VARCHAR(300) NOT NULL,
                    is_builtin BOOLEAN NOT NULL,
                    source_path VARCHAR(500),
                    source_sha256 VARCHAR(64),
                    source_encoding VARCHAR(30),
                    source_size BIGINT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE jobs (
                    id VARCHAR(100) PRIMARY KEY,
                    project_id VARCHAR(100) NOT NULL,
                    model_profile_id VARCHAR(100) NOT NULL,
                    status VARCHAR(30) NOT NULL,
                    worker_id VARCHAR(100),
                    lease_expires_at DATETIME,
                    error_code VARCHAR(100),
                    completed_chunks INTEGER NOT NULL,
                    total_chunks INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO projects (
                    id, title, is_builtin, source_path, source_sha256,
                    source_encoding, source_size, created_at, updated_at
                ) VALUES (
                    'p-legacy', 'Legacy', 0, 'p-legacy/source.txt',
                    'abc', 'utf-8', 4,
                    '2026-01-01 00:00:00', '2026-01-01 00:00:00'
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO jobs (
                    id, project_id, model_profile_id, status,
                    completed_chunks, total_chunks, created_at, updated_at
                ) VALUES (
                    'job-legacy', 'p-legacy', 'fixed:test', 'QUEUED',
                    0, 0, '2026-01-01 00:00:00', '2026-01-01 00:00:00'
                )
                """
            )
        )

    repository = JobRepository(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("jobs")}
    assert "kind" in columns
    assert repository.get("job-legacy").kind == JobKind.FULL_BUILD


def test_concurrent_legacy_schema_initialization_is_idempotent(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}")
    JobRepository(engine)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE jobs DROP COLUMN kind"))

    inspection_barrier = Barrier(2)
    inspection_count = 0
    inspection_lock = Lock()

    @event.listens_for(engine, "before_cursor_execute")
    def synchronize_kind_inspection(
        connection, cursor, statement, parameters, context, executemany
    ):
        nonlocal inspection_count
        if "table_xinfo" not in statement or "jobs" not in statement:
            return
        with inspection_lock:
            inspection_count += 1
            should_wait = inspection_count <= 2
        if should_wait:
            inspection_barrier.wait(timeout=5)

    with ThreadPoolExecutor(max_workers=2) as executor:
        initializers = [executor.submit(JobRepository, engine) for _ in range(2)]
        repositories = [
            initializer.result(timeout=5) for initializer in initializers
        ]

    assert len(repositories) == 2
    columns = {column["name"] for column in inspect(engine).get_columns("jobs")}
    assert "kind" in columns


def test_schema_upgrade_does_not_swallow_unrelated_operational_error(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'locked.db'}")
    JobRepository(engine)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE jobs DROP COLUMN kind"))

    @event.listens_for(engine, "before_cursor_execute")
    def fail_alter(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("ALTER TABLE jobs ADD COLUMN kind"):
            raise OperationalError(
                statement, parameters, Exception("database is locked")
            )

    with pytest.raises(OperationalError, match="database is locked"):
        JobRepository(engine)


def test_create_defaults_to_full_build_and_records_kind_in_event():
    repository = JobRepository(create_engine("sqlite+pysqlite:///:memory:"))

    job = repository.create("p-1", "fixed:test")

    assert job.kind == JobKind.FULL_BUILD
    assert repository.events_after(job.id, 0)[0].snapshot["kind"] == "FULL_BUILD"


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


def test_update_progress_is_monotonic_and_emits_snapshots():
    repository = JobRepository(create_engine("sqlite+pysqlite:///:memory:"))
    job = repository.create("p-1", "fixed:test")

    assert repository.update_progress(job.id, 0, 3) is True
    assert repository.update_progress(job.id, 1, 3) is True
    updated = repository.get_required(job.id)

    assert (updated.completed_chunks, updated.total_chunks) == (1, 3)
    assert repository.events_after(job.id, 0)[-1].snapshot[
        "completed_chunks"
    ] == 1


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
