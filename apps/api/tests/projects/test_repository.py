from sqlalchemy import create_engine

from app.projects.repository import ProjectRepository


def test_ensure_builtin_project_is_idempotent() -> None:
    repository = ProjectRepository(create_engine("sqlite+pysqlite:///:memory:"))

    first = repository.ensure_builtin_project("xiaoao", "笑傲江湖")
    second = repository.ensure_builtin_project("xiaoao", "不同标题不会覆盖")

    assert first.id == "xiaoao"
    assert first.is_builtin is True
    assert second.title == "笑傲江湖"
    assert repository.count() == 1


def test_create_user_project_persists_upload_metadata() -> None:
    repository = ProjectRepository(create_engine("sqlite+pysqlite:///:memory:"))

    project = repository.create_user_project(
        project_id="p-1",
        title="测试小说",
        source_path="p-1/source.txt",
        source_sha256="abc",
        source_encoding="utf-8",
        source_size=12,
    )

    assert project.is_builtin is False
    assert project.source_sha256 == "abc"
    assert [item.id for item in repository.list_projects()] == ["p-1"]
