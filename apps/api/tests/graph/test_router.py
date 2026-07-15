from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from app.graph.router import get_repository
from app.main import app


def test_neighborhood_rejects_unbounded_depth() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/graph/neighborhood",
            params={"project_id": "xiaoao", "entity_id": "x", "depth": 4},
        )

    assert response.status_code == 422


def test_neighborhood_filters_rejected_edges_at_service_boundary() -> None:
    class Repository:
        def neighborhood(
            self,
            project_id: str,
            entity_id: str,
            depth: int,
            limit: int,
            from_chapter: int | None,
            to_chapter: int | None,
        ):
            return {
                "nodes": [
                    {
                        "id": "linghu",
                        "project_id": project_id,
                        "type": "Person",
                        "name": "令狐冲",
                        "aliases": [],
                        "description": "",
                    }
                ],
                "edges": [
                    {
                        "id": "fact-rejected",
                        "source_id": "yue",
                        "target_id": "linghu",
                        "type": "MASTER_OF",
                        "confidence": 1,
                        "review_status": "REJECTED",
                    },
                    {
                        "id": "fact-accepted",
                        "source_id": "feng",
                        "target_id": "linghu",
                        "type": "MASTER_OF",
                        "confidence": 1,
                        "review_status": "ACCEPTED",
                    },
                ],
            }

    app.dependency_overrides[get_repository] = lambda: Repository()
    try:
        response = TestClient(app).get(
            "/api/graph/neighborhood",
            params={"project_id": "xiaoao", "entity_id": "linghu", "depth": 1},
        )
    finally:
        app.dependency_overrides.pop(get_repository, None)

    assert response.status_code == 200
    assert all(edge["id"] != "fact-rejected" for edge in response.json()["edges"])


def test_search_rejects_excessive_limit() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/api/graph/search",
            params={"project_id": "xiaoao", "query": "令狐", "limit": 51},
        )

    assert response.status_code == 422


def test_entity_detail_serializes_attributes_and_relations() -> None:
    class Repository:
        def entity_detail(self, project_id: str, entity_id: str):
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
                        "confidence": 1,
                        "evidence": [],
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
                        "evidence": None,
                    }
                ],
            }

    app.dependency_overrides[get_repository] = lambda: Repository()
    try:
        response = TestClient(app).get(
            "/api/entities/linghu", params={"project_id": "p-1"}
        )
    finally:
        app.dependency_overrides.pop(get_repository, None)

    body = response.json()
    assert response.status_code == 200
    assert body["attributes"][0]["label"] == "身份"
    assert body["relations"][0]["other"]["name"] == "岳不群"
    assert body["facts"][0]["id"] == "fact-master"


def test_relation_detail_serializes_evidence() -> None:
    class Repository:
        def relation_detail(self, project_id: str, relation_id: str):
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

    app.dependency_overrides[get_repository] = lambda: Repository()
    try:
        response = TestClient(app).get(
            "/api/graph/relations/fact-master", params={"project_id": "p-1"}
        )
    finally:
        app.dependency_overrides.pop(get_repository, None)

    assert response.status_code == 200
    assert response.json()["evidence"][0]["quote"] == "岳不群传授令狐冲"
    assert response.json()["label"] == "师父"
    assert response.json()["source"]["name"] == "岳不群"


def test_relation_detail_returns_not_found_for_missing_relation() -> None:
    class Repository:
        def relation_detail(self, project_id: str, relation_id: str):
            return None

    app.dependency_overrides[get_repository] = lambda: Repository()
    try:
        response = TestClient(app).get(
            "/api/graph/relations/missing", params={"project_id": "p-1"}
        )
    finally:
        app.dependency_overrides.pop(get_repository, None)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ENTITY_NOT_FOUND"


def test_timeline_detail_serializes_classified_relationship_states() -> None:
    class Repository:
        def timeline_detail(self, project_id: str, event_id: str):
            person = {"id": "linghu", "project_id": project_id, "type": "Person", "name": "令狐冲", "aliases": [], "description": ""}
            return {
                "event": {"id": event_id, "project_id": project_id, "type": "Event", "name": "思过崖传剑", "aliases": [], "description": ""},
                "chapter_number": 10,
                "participants": [person],
                "evidence": [],
                "relationships": [{
                    "id": "fact-knows",
                    "type": "KNOWS",
                    "source": person,
                    "target": {"id": "dugu", "project_id": project_id, "type": "Swordplay", "name": "独孤九剑", "aliases": [], "description": ""},
                    "from_chapter": 10,
                    "to_chapter": None,
                }],
            }

    app.dependency_overrides[get_repository] = lambda: Repository()
    try:
        response = TestClient(app).get(
            "/api/graph/timeline/event-1", params={"project_id": "p-1"}
        )
    finally:
        app.dependency_overrides.pop(get_repository, None)

    assert response.status_code == 200
    assert response.json()["relationship_states"]["started"][0]["label"] == "掌握"


def test_timeline_detail_returns_not_found_for_missing_event() -> None:
    class Repository:
        def timeline_detail(self, project_id: str, event_id: str):
            return None

    app.dependency_overrides[get_repository] = lambda: Repository()
    try:
        response = TestClient(app).get(
            "/api/graph/timeline/missing", params={"project_id": "p-1"}
        )
    finally:
        app.dependency_overrides.pop(get_repository, None)

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ENTITY_NOT_FOUND"


def test_app_lifespan_reuses_and_closes_one_neo4j_driver() -> None:
    driver = Mock()

    with patch("app.main.GraphDatabase.driver", return_value=driver) as create_driver:
        with TestClient(app) as client:
            first = client.get("/api/health")
            second = client.get("/api/health")

    assert first.status_code == 200
    assert second.status_code == 200
    create_driver.assert_called_once()
    driver.close.assert_called_once_with()


def test_get_repository_wraps_shared_driver_without_owning_it() -> None:
    driver = Mock()
    request = Mock()
    request.app.state.neo4j_driver = driver

    first = get_repository(request)
    second = get_repository(request)

    assert first is not second
    assert first.driver is driver
    assert second.driver is driver
    driver.close.assert_not_called()
