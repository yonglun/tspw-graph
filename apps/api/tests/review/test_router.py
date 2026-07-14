from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.dependencies import require_ready_admin
from app.auth.models import AdminAccount
from app.review.router import router


app = FastAPI()
app.include_router(router)
app.dependency_overrides[require_ready_admin] = lambda: AdminAccount(
    id="admin-test", username="admin", normalized_username="admin", password_hash="hash"
)
client = TestClient(app)


def test_review_scan_and_items_endpoint():
    response = client.post("/api/projects/xiaoao/review/scan")
    assert response.status_code == 200
    body = response.json()
    assert "created_items" in body

    items = client.get("/api/projects/xiaoao/review/items?status=OPEN&limit=20")
    assert items.status_code == 200
    assert isinstance(items.json()["items"], list)


def test_manual_review_item_and_action_endpoint():
    create = client.post(
        "/api/projects/xiaoao/review/items",
        json={
            "item_type": "FACT",
            "reason_code": "MANUAL_REVIEW",
            "target": {"fact_id": "manual-fact"},
            "evidence_ids": [],
            "fingerprint": "manual:manual-fact",
            "severity": 10,
        },
    )
    assert create.status_code == 200
    item_id = create.json()["id"]

    action = client.post(
        f"/api/projects/xiaoao/review/items/{item_id}/actions",
        json={
            "action_type": "dismiss_item",
            "payload": {},
            "idempotency_key": "dismiss-manual-fact",
        },
    )
    assert action.status_code == 200
    assert action.json()["item"]["status"] == "DISMISSED"
