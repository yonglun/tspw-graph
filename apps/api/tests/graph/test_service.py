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


def test_entity_detail_includes_attributes_and_relation_summaries() -> None:
    class Repository:
        def entity_detail(self, project_id, entity_id):
            return {
                "entity": {
                    "id": entity_id,
                    "project_id": project_id,
                    "type": "Person",
                    "name": "令狐冲",
                    "aliases": [],
                    "description": "",
                },
                "attributes": [
                    {
                        "id": "attr-identity",
                        "property_id": "identity",
                        "value_type": "TEXT",
                        "value": "华山派大弟子",
                        "confidence": 0.96,
                        "evidence": [
                            {
                                "id": "ev-attr",
                                "chapter_id": "chapter-1",
                                "chapter_number": 1,
                                "chapter_title": "第一章",
                                "start_offset": 10,
                                "end_offset": 16,
                                "quote": "华山派大弟子",
                            }
                        ],
                    }
                ],
                "rows": [
                    {
                        "id": "fact-master",
                        "type": "MASTER_OF",
                        "source_id": "yue",
                        "target_id": entity_id,
                        "review_status": "ACCEPTED",
                        "source": {"id": "yue", "type": "Person", "name": "岳不群"},
                        "target": {"id": entity_id, "type": "Person", "name": "令狐冲"},
                        "evidence": {
                            "id": "ev-fact",
                            "chapter_id": "chapter-1",
                            "chapter_number": 1,
                            "chapter_title": "第一章",
                            "start_offset": 20,
                            "end_offset": 26,
                            "quote": "岳不群传授令狐冲",
                        },
                    }
                ],
            }

    detail = GraphService(Repository()).entity_detail("p-1", "linghu")

    assert detail.attributes[0].property_id == "identity"
    assert detail.attributes[0].label == "身份"
    assert detail.attributes[0].value == "华山派大弟子"
    assert detail.attributes[0].evidence[0].quote == "华山派大弟子"
    assert detail.relations[0].fact_id == "fact-master"
    assert detail.relations[0].label == "师父"
    assert detail.relations[0].direction == "INCOMING"
    assert detail.relations[0].other.name == "岳不群"
    assert detail.facts[0].evidence[0].quote == "岳不群传授令狐冲"


def test_relation_detail_returns_relation_evidence() -> None:
    class Repository:
        def relation_detail(self, project_id, relation_id):
            return {
                "id": relation_id,
                "type": "MASTER_OF",
                "source_id": "yue",
                "target_id": "linghu",
                "source": {"id": "yue", "project_id": project_id, "type": "Person", "name": "岳不群", "aliases": [], "description": ""},
                "target": {"id": "linghu", "project_id": project_id, "type": "Person", "name": "令狐冲", "aliases": [], "description": ""},
                "review_status": "ACCEPTED",
                "evidence": [
                    {
                        "id": "ev-master",
                        "chapter_id": "chapter-1",
                        "chapter_number": 1,
                        "chapter_title": "第一章",
                        "start_offset": 20,
                        "end_offset": 30,
                        "quote": "岳不群传授令狐冲",
                    }
                ],
            }

    relation = GraphService(Repository()).relation_detail("p-1", "fact-master")

    assert relation.id == "fact-master"
    assert relation.type == "MASTER_OF"
    assert relation.label == "师父"
    assert relation.source is not None and relation.source.name == "岳不群"
    assert relation.target is not None and relation.target.name == "令狐冲"
    assert relation.evidence[0].quote == "岳不群传授令狐冲"


def test_missing_relation_detail_raises_not_found() -> None:
    class Repository:
        def relation_detail(self, project_id, relation_id):
            return None

    with pytest.raises(EntityNotFoundError):
        GraphService(Repository()).relation_detail("p-1", "missing")


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


class FakeNode(dict):
    pass


class FakeEdge(dict):
    def __init__(self, source_id: str, target_id: str, **values):
        super().__init__(**values)
        self.start_node = FakeNode(id=source_id)
        self.end_node = FakeNode(id=target_id)


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
    assert "CALL {" in session.statement
    assert session.statement.index("LIMIT $limit") < session.statement.index("collect(edge)")


def test_depth_two_query_stays_bounded() -> None:
    session = FakeSession(None)
    repository = Neo4jGraphRepository(FakeDriver(session))

    result = repository.neighborhood("p-1", "linghu", 2, 50, None, None)

    assert result is None
    assert "RELATED*1..2" in session.statement
    assert "CALL {" in session.statement
    assert session.statement.index("LIMIT $limit") < session.statement.index("collect(path)")


def test_depth_two_returns_an_isolated_valid_center() -> None:
    center = FakeNode(id="center", project_id="p-1", type="Person", name="中心")
    session = FakeSession({"nodes": [center], "edges": []})
    repository = Neo4jGraphRepository(FakeDriver(session))

    result = repository.neighborhood("p-1", "center", 2, 50, None, None)

    assert result == {"nodes": [dict(center)], "edges": []}
    center_match = session.statement.index("MATCH (center:Entity")
    subquery = session.statement.index("CALL {")
    assert center_match < subquery


def test_neighborhood_caps_nodes_after_deduplication_and_drops_trimmed_edges() -> None:
    center = FakeNode(id="center", project_id="p-1", type="Person", name="中心")
    first = FakeNode(id="first", project_id="p-1", type="Person", name="甲")
    second = FakeNode(id="second", project_id="p-1", type="Person", name="乙")
    duplicate_second = FakeNode(id="second", project_id="p-1", type="Person", name="乙")
    session = FakeSession(
        {
            "nodes": [center, first, second, duplicate_second],
            "edges": [
                FakeEdge("center", "first", id="edge-1", type="ALLY_OF"),
                FakeEdge("first", "second", id="edge-2", type="ALLY_OF"),
            ],
        }
    )
    repository = Neo4jGraphRepository(FakeDriver(session))

    result = repository.neighborhood("p-1", "center", 2, 2, None, None)

    assert result == {
        "nodes": [dict(center), dict(first)],
        "edges": [
            {
                "id": "edge-1",
                "type": "ALLY_OF",
                "source_id": "center",
                "target_id": "first",
            }
        ],
    }


def test_entity_detail_query_aggregates_attributes_and_facts_separately() -> None:
    entity = {
        "id": "linghu",
        "project_id": "p-1",
        "type": "Person",
        "name": "令狐冲",
    }
    session = FakeSession({"entity": entity, "attributes": [], "rows": []})
    repository = Neo4jGraphRepository(FakeDriver(session))

    result = repository.entity_detail("p-1", "linghu")

    assert result == {"entity": entity, "attributes": [], "rows": []}
    assert session.statement.count("CALL {") == 2
    assert "HAS_ATTRIBUTE" in session.statement
    assert "(fact:Fact)-[:SOURCE|TARGET]->(entity)" in session.statement


def test_relation_detail_query_aggregates_evidence_before_returning_relation() -> None:
    relation = {
        "id": "fact-master",
        "type": "MASTER_OF",
        "source_id": "yue",
        "target_id": "linghu",
        "review_status": "ACCEPTED",
        "evidence": [
            {
                "id": "ev-1",
                "chapter_id": "chapter-1",
                "chapter_number": 1,
                "chapter_title": "第一章",
                "start_offset": 1,
                "end_offset": 4,
                "quote": "传剑",
            }
        ],
    }
    session = FakeSession({"relation": relation})
    repository = Neo4jGraphRepository(FakeDriver(session))

    result = repository.relation_detail("p-1", "fact-master")

    assert result == relation
    assert "WITH fact, source, target, collect(DISTINCT" in session.statement
    assert "evidence: [item IN evidence_rows WHERE item.id IS NOT NULL]" in session.statement
