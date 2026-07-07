from fastapi.testclient import TestClient

from app.graph.router import get_repository
from app.main import app


def test_neighborhood_rejects_unbounded_depth(client: TestClient) -> None:
    response = client.get(
        "/api/graph/neighborhood",
        params={"project_id": "xiaoao", "entity_id": "x", "depth": 4},
    )

    assert response.status_code == 422


def test_neighborhood_filters_rejected_edges_at_service_boundary() -> None:
    class Repository:
        def entity_exists(self, project_id: str, entity_id: str) -> bool:
            return True

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


def test_search_rejects_excessive_limit(client: TestClient) -> None:
    response = client.get(
        "/api/graph/search",
        params={"project_id": "xiaoao", "query": "令狐", "limit": 51},
    )

    assert response.status_code == 422
