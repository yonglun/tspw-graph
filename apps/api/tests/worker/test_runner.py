from sqlalchemy import create_engine

from app.extraction.providers import ProviderError, ProviderErrorKind
from app.jobs.models import JobKind, JobStatus
from app.jobs.repository import JobRepository
from app.worker.runner import WorkerRunner
from app.worker.online import OnlineBuildHandlers
from app.projects.repository import ProjectRepository
from app.projects.files import UploadStore
from app.projects.service import ProjectUploadService
from app.extraction.pipeline import ExtractionPipeline
from app.graph.importer import GraphImporter
from app.settings import Settings
from io import BytesIO


class Handler:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, job) -> None:
        self.calls += 1


def test_runner_does_not_repeat_completed_stage():
    repository = JobRepository(create_engine("sqlite+pysqlite:///:memory:"))
    job = repository.create("p-1", "fixed:test")
    repository.set_status(job.id, JobStatus.EXTRACTING)
    splitter = Handler()
    extractor = Handler()
    runner = WorkerRunner(
        repository,
        worker_id="w-1",
        handlers={JobStatus.SPLITTING: splitter, JobStatus.EXTRACTING: extractor},
    )

    runner.run_once()

    assert splitter.calls == 0
    assert extractor.calls == 1
    assert repository.get(job.id).status == JobStatus.RESOLVING


def test_runner_preserves_provider_error_code(caplog):
    repository = JobRepository(create_engine("sqlite+pysqlite:///:memory:"))
    job = repository.create("p-1", "azure:gpt-4o")

    def fail_with_provider_error(job):
        raise ProviderError(ProviderErrorKind.CONFIGURATION, "MODEL_HTTP_400")

    runner = WorkerRunner(
        repository,
        worker_id="w-1",
        handlers={JobStatus.SPLITTING: fail_with_provider_error},
    )

    runner.run_once()

    failed = repository.get(job.id)
    assert failed.status == JobStatus.FAILED
    assert failed.error_code == "MODEL_HTTP_400"
    assert "Worker stage failed" in caplog.text
    assert job.id in caplog.text


def test_runner_logs_unexpected_stage_failure(caplog):
    repository = JobRepository(create_engine("sqlite+pysqlite:///:memory:"))
    job = repository.create("p-1", "fixed:test")

    def fail_unexpectedly(job):
        raise RuntimeError("boom")

    runner = WorkerRunner(
        repository,
        worker_id="w-1",
        handlers={JobStatus.SPLITTING: fail_unexpectedly},
    )

    runner.run_once()

    failed = repository.get(job.id)
    assert failed.status == JobStatus.FAILED
    assert failed.error_code == "WORKER_STAGE_FAILED"
    assert "Worker stage failed" in caplog.text
    assert job.id in caplog.text


def test_online_handlers_complete_fixed_provider_job(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    projects = ProjectRepository(engine)
    uploads = UploadStore(tmp_path / "uploads")
    project = ProjectUploadService(projects, uploads).create(
        title="测试", filename="book.txt", stream=BytesIO("第一章\n甲识乙".encode())
    )
    jobs = JobRepository(engine)
    job = jobs.create(project.id, "fixed:test")

    class Writer:
        def ensure_constraints(self): pass
        def upsert_batch(self, label, rows): return len(rows)

    handlers = OnlineBuildHandlers(
        projects=projects, jobs=jobs, uploads=uploads,
        pipeline=ExtractionPipeline(GraphImporter(Writer())),
        settings=Settings(data_root=uploads.root),
    ).mapping()
    runner = WorkerRunner(jobs, worker_id="w", handlers=handlers)
    for _ in range(5):
        runner.run_once()
    assert jobs.get(job.id).status == JobStatus.COMPLETED
    assert jobs.get_quality(job.id)["total_chunks"] == 1


def test_attribute_backfill_only_writes_attributes_and_their_evidence(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'db.sqlite'}")
    projects = ProjectRepository(engine)
    uploads = UploadStore(tmp_path / "uploads")
    project = ProjectUploadService(projects, uploads).create(
        title="测试",
        filename="book.txt",
        stream=BytesIO("第一章\n测试人物甲是华山派大弟子".encode()),
    )
    jobs = JobRepository(engine)
    job = jobs.create(project.id, "fixed:test", JobKind.ATTRIBUTE_BACKFILL)

    class RecordingWriter:
        def __init__(self):
            self.labels = []
            self.rows = {}

        def ensure_constraints(self):
            pass

        def upsert_batch(self, label, rows):
            self.labels.append(label)
            self.rows[label] = rows
            return len(rows)

    writer = RecordingWriter()
    handlers = OnlineBuildHandlers(
        projects=projects,
        jobs=jobs,
        uploads=uploads,
        pipeline=ExtractionPipeline(GraphImporter(writer)),
        settings=Settings(data_root=uploads.root),
    ).mapping()
    runner = WorkerRunner(jobs, worker_id="w", handlers=handlers)

    for _ in range(5):
        runner.run_once()

    assert set(writer.labels) <= {"Evidence", "AttributeAssertion"}
    assert writer.labels == ["Evidence", "AttributeAssertion"]
    assert len(writer.rows["Evidence"]) == 1
    assert len(writer.rows["AttributeAssertion"]) == 1
    assert jobs.get(job.id).status == JobStatus.COMPLETED
