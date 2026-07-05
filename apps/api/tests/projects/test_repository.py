from sqlalchemy import create_engine

from app.projects.repository import ProjectRepository


def test_ensure_builtin_project_is_idempotent() -> None:
    repository = ProjectRepository(create_engine("sqlite+pysqlite:///:memory:"))

    first = repository.ensure_builtin_project("xiaoao", "笑傲江湖")
    second = repository.ensure_builtin_project("xiaoao", "不同标题不会覆盖")

    assert first.id == "xiaoao"
    assert second.title == "笑傲江湖"
    assert repository.count() == 1
