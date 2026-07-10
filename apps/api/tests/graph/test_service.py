import pytest

from app.graph.repository import Neo4jGraphRepository
from app.graph.service import EntityNotFoundError, GraphService


class FakeRepository:
    def search_exact(self, project_id: str, query: str, types: list[str], limit: int):
        return [
            {"id": "p1", "project_id": project_id, "type": "Person", "name": "令狐沖", "aliases": ["令狐冲"], "description": ""}
        ]

    def search_contains(
        self, project_id: str, query: str, types: list[str], limit: int
    ):
        return []


def test_search_never_returns_other_project() -> None:
    rows = GraphService(FakeRepository()).search("xiaoao", "令狐", [], 20)

    assert rows
    assert all(row.project_id == "xiaoao" for row in rows)


def test_search_returns_exact_results_first_and_deduplicates_fallback() -> None:
    class Repository:
        def __init__(self) -> None:
            self.calls: list[tuple[str, int]] = []

        def search_exact(self, project_id, query, types, limit):
            self.calls.append(("exact", limit))
            return [
                {
                    "id": "linghu",
                    "project_id": project_id,
                    "type": "Person",
                    "name": "令狐冲",
                }
            ]

        def search_contains(self, project_id, query, types, limit):
            self.calls.append(("contains", limit))
            return [
                {
                    "id": "linghu",
                    "project_id": project_id,
                    "type": "Person",
                    "name": "令狐冲",
                },
                {
                    "id": "linghu-jianfa",
                    "project_id": project_id,
                    "type": "MartialArt",
                    "name": "令狐剑法",
                },
            ]

    repository = Repository()
    results = GraphService(repository).search("p-1", "令狐冲", [], 20)

    assert repository.calls == [("exact", 20), ("contains", 19)]
    assert results[0].name == "令狐冲"
    assert [item.id for item in results] == ["linghu", "linghu-jianfa"]


def test_search_skips_fallback_when_exact_results_fill_limit() -> None:
    class Repository:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def search_exact(self, project_id, query, types, limit):
            self.calls.append("exact")
            return [
                {"id": "a", "project_id": project_id, "type": "Person", "name": "A"},
                {"id": "b", "project_id": project_id, "type": "Person", "name": "B"},
            ]

        def search_contains(self, project_id, query, types, limit):
            self.calls.append("contains")
            return []

    repository = Repository()
    results = GraphService(repository).search("p-1", "A", [], 2)

    assert [item.id for item in results] == ["a", "b"]
    assert repository.calls == ["exact"]


def test_search_filters_other_projects_from_both_query_paths() -> None:
    class Repository:
        def search_exact(self, project_id, query, types, limit):
            return [
                {"id": "wrong", "project_id": "p-2", "type": "Person", "name": query}
            ]

        def search_contains(self, project_id, query, types, limit):
            return [
                {"id": "right", "project_id": project_id, "type": "Person", "name": query},
                {"id": "wrong-2", "project_id": "p-2", "type": "Person", "name": query},
            ]

    results = GraphService(Repository()).search("p-1", "令狐冲", [], 20)

    assert [item.id for item in results] == ["right"]


def test_one_hop_neighborhood_does_not_require_existence_query() -> None:
    class Repository:
        def neighborhood(self, *args):
            return {
                "nodes": [
                    {
                        "id": "linghu",
                        "project_id": "p-1",
                        "type": "Person",
                        "name": "令狐冲",
                    }
                ],
                "edges": [],
            }

    result = GraphService(Repository()).neighborhood(
        "p-1", "linghu", 1, 50, None, None
    )

    assert [node.id for node in result.nodes] == ["linghu"]
    assert result.edges == []


def test_missing_neighborhood_center_raises_not_found() -> None:
    class Repository:
        def neighborhood(self, *args):
            return None

    with pytest.raises(EntityNotFoundError):
        GraphService(Repository()).neighborhood("p-1", "missing", 1, 50, None, None)


class FakeResult:
    def __init__(self, record):
        self.record = record

    def __iter__(self):
        return iter([])

    def single(self):
        return self.record


class FakeSession:
    def __init__(self, record=None) -> None:
        self.record = record
        self.statement = ""
        self.parameters = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def run(self, statement, **parameters):
        self.statement = statement
        self.parameters = parameters
        return FakeResult(self.record)


class FakeDriver:
    def __init__(self, session: FakeSession) -> None:
        self.fake_session = session

    def session(self):
        return self.fake_session


def test_exact_search_uses_composite_index_compatible_equalities() -> None:
    session = FakeSession()
    repository = Neo4jGraphRepository(FakeDriver(session))

    repository.search_exact("p-1", "令狐冲", [], 20)

    assert "n.project_id = $project_id AND n.name = $search_text" in session.statement
    assert "CONTAINS" not in session.statement


def test_one_hop_query_returns_center_without_edges_and_matches_related_directly() -> None:
    center = {
        "id": "linghu",
        "project_id": "p-1",
        "type": "Person",
        "name": "令狐冲",
    }
    session = FakeSession({"nodes": [center], "edges": []})
    repository = Neo4jGraphRepository(FakeDriver(session))

    result = repository.neighborhood("p-1", "linghu", 1, 50, None, None)

    assert result == {"nodes": [center], "edges": []}
    assert "[edge:RELATED]" in session.statement
    assert "RELATED*" not in session.statement


def test_depth_two_query_stays_bounded() -> None:
    session = FakeSession(None)
    repository = Neo4jGraphRepository(FakeDriver(session))

    result = repository.neighborhood("p-1", "linghu", 2, 50, None, None)

    assert result is None
    assert "RELATED*1..2" in session.statement
