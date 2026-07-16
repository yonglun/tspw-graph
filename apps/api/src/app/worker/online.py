from collections.abc import Callable, Mapping

from app.extraction.pipeline import ExtractionPipeline, PipelineCancelled
from app.extraction.providers import ProviderRegistry
from app.jobs.models import Job, JobKind, JobStatus
from app.jobs.repository import JobRepository
from app.projects.files import UploadStore
from app.projects.repository import ProjectRepository
from app.settings import Settings


class OnlineBuildHandlers:
    def __init__(
        self,
        *,
        projects: ProjectRepository,
        jobs: JobRepository,
        uploads: UploadStore,
        pipeline: ExtractionPipeline,
        settings: Settings,
    ) -> None:
        self.projects = projects
        self.jobs = jobs
        self.uploads = uploads
        self.pipeline = pipeline
        self.providers = ProviderRegistry(settings)

    def mapping(self) -> Mapping[JobStatus, Callable[[Job], None]]:
        return {
            JobStatus.SPLITTING: self._checkpoint,
            JobStatus.EXTRACTING: self._checkpoint,
            JobStatus.RESOLVING: self._checkpoint,
            JobStatus.VALIDATING: self._checkpoint,
            JobStatus.IMPORTING: self._build,
        }

    def _checkpoint(self, job: Job) -> None:
        return None

    def _build(self, job: Job) -> None:
        project = self.projects.get(job.project_id)
        if project is None or not project.source_path:
            raise RuntimeError("PROJECT_SOURCE_MISSING")
        source = (self.uploads.root / project.source_path).read_text(encoding="utf-8")
        attributes_only = JobKind(job.kind) == JobKind.ATTRIBUTE_BACKFILL
        try:
            result = self.pipeline.process(
                project.id,
                project.title,
                source,
                self.providers.create(job.model_profile_id),
                attributes_only=attributes_only,
                on_progress=lambda completed, total: self._update_progress(
                    job.id, completed, total
                ),
                should_cancel=lambda: self._is_cancelled(job.id),
            )
        except PipelineCancelled:
            return
        self.jobs.save_quality(job.id, result.quality.model_dump())

    def _update_progress(
        self, job_id: str, completed_chunks: int, total_chunks: int
    ) -> None:
        if not self.jobs.update_progress(
            job_id, completed_chunks, total_chunks
        ):
            raise PipelineCancelled("JOB_CANCELLED")

    def _is_cancelled(self, job_id: str) -> bool:
        return self.jobs.get_required(job_id).status == JobStatus.CANCELLED
