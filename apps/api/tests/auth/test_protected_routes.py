import pytest
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/projects/upload"),
        ("post", "/api/projects/p-1/attribute-jobs"),
        ("delete", "/api/projects/p-1"),
        ("get", "/api/model-profiles"),
        ("get", "/api/jobs/job-1"),
        ("post", "/api/jobs/job-1/cancel"),
        ("get", "/api/projects/p-1/review/items"),
        ("post", "/api/projects/p-1/review/items"),
    ],
)
def test_anonymous_management_routes_are_rejected(method, path):
    response = getattr(client, method)(path)
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "AUTHENTICATION_REQUIRED"


def test_public_project_and_ontology_reads_remain_anonymous():
    assert client.get("/api/projects").status_code != 401
    assert client.get("/api/ontology").status_code != 401
