from fastapi.testclient import TestClient

from app.extraction.providers import ProviderError, ProviderErrorKind
from app.graph.router import get_repository
from app.main import app
from app.qa.router import get_intent_provider
from app.qa.service import NO_FACTS


class Repository:
    def search(self, project_id, query, types, limit):
        return []

    def entity_detail(self, project_id, entity_id):
        return None


class Provider:
    def parse(self, question, catalog):
        raise ProviderError(ProviderErrorKind.INVALID_RESPONSE, "MODEL_RESPONSE_INVALID")


def test_qa_router_accepts_server_side_provider_dependency():
    app.dependency_overrides[get_repository] = lambda: Repository()
    app.dependency_overrides[get_intent_provider] = lambda: Provider()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/ask",
                json={"project_id": "p-1", "question": "未知问题"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["answer"] == NO_FACTS
