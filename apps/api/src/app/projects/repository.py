from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from app.projects.models import Base, Project


class ProjectRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        Base.metadata.create_all(engine)

    def ensure_builtin_project(self, project_id: str, title: str) -> Project:
        with Session(self.engine) as session:
            project = session.get(Project, project_id)
            if project is None:
                project = Project(id=project_id, title=title, is_builtin=True)
                session.add(project)
                session.commit()
            session.refresh(project)
            session.expunge(project)
            return project

    def create_user_project(
        self,
        *,
        project_id: str,
        title: str,
        source_path: str,
        source_sha256: str,
        source_encoding: str,
        source_size: int,
    ) -> Project:
        with Session(self.engine) as session:
            project = Project(
                id=project_id,
                title=title,
                is_builtin=False,
                source_path=source_path,
                source_sha256=source_sha256,
                source_encoding=source_encoding,
                source_size=source_size,
            )
            session.add(project)
            session.commit()
            session.refresh(project)
            session.expunge(project)
            return project

    def get(self, project_id: str) -> Project | None:
        with Session(self.engine) as session:
            project = session.get(Project, project_id)
            if project is not None:
                session.expunge(project)
            return project

    def list_projects(self) -> list[Project]:
        with Session(self.engine) as session:
            projects = list(session.scalars(select(Project).order_by(Project.created_at)))
            for project in projects:
                session.expunge(project)
            return projects

    def delete(self, project_id: str) -> None:
        with Session(self.engine) as session:
            project = session.get(Project, project_id)
            if project is not None:
                session.delete(project)
                session.commit()

    def count(self) -> int:
        with Session(self.engine) as session:
            return session.scalar(select(func.count()).select_from(Project)) or 0
