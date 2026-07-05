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
                project = Project(id=project_id, title=title)
                session.add(project)
                session.commit()
            session.refresh(project)
            session.expunge(project)
            return project

    def count(self) -> int:
        with Session(self.engine) as session:
            return session.scalar(select(func.count()).select_from(Project)) or 0
