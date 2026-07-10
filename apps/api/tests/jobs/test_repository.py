from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, inspect, text

from app.jobs.models import InvalidJobTransition, JobKind, JobStatus, transition
from app.jobs.repository import JobRepository


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
        connection.execute(
            text(
                """
                CREATE TABLE projects (
                    id VARCHAR(100) PRIMARY KEY,
                    title VARCHAR(300) NOT NULL,
                    is_builtin BOOLEAN NOT NULL,
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
                    updated_at DATETIME NOT NULL
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


def test_create_defaults_to_full_build_and_records_kind_in_event():
    repository = JobRepository(create_engine("sqlite+pysqlite:///:memory:"))

    job = repository.create("p-1", "fixed:test")

    assert job.kind == JobKind.FULL_BUILD
    assert repository.events_after(job.id, 0)[0].snapshot["kind"] == "FULL_BUILD"
