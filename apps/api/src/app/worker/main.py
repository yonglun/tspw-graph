import logging
import time
from uuid import uuid4

from sqlalchemy import create_engine

from app.jobs.repository import JobRepository
from app.extraction.pipeline import ExtractionPipeline
from app.graph.importer import GraphImporter
from app.graph.neo4j import Neo4jGraphWriter
from app.projects.files import UploadStore
from app.projects.repository import ProjectRepository
from app.settings import get_settings
from app.worker.online import OnlineBuildHandlers
from app.worker.runner import WorkerRunner


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> None:
    configure_logging()
    settings = get_settings()
    engine = create_engine(settings.sqlite_url)
    jobs = JobRepository(engine)
    projects = ProjectRepository(engine)
    uploads = UploadStore(settings.data_root, settings.max_upload_bytes)
    graph = Neo4jGraphWriter.from_settings(settings)
    handlers = OnlineBuildHandlers(
        projects=projects,
        jobs=jobs,
        uploads=uploads,
        pipeline=ExtractionPipeline(GraphImporter(graph)),
        settings=settings,
    ).mapping()
    runner = WorkerRunner(
        jobs,
        worker_id=f"worker-{uuid4()}",
        handlers=handlers,
    )
    try:
        while True:
            if not runner.run_once():
                time.sleep(1)
    finally:
        graph.close()


if __name__ == "__main__":
    main()
