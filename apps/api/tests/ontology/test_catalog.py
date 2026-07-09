from fastapi.testclient import TestClient


def test_catalog_contains_tbox_and_abox_example(client: TestClient) -> None:
    response = client.get("/api/ontology")

    assert response.status_code == 200
    body = response.json()
    assert {item["id"] for item in body["entity_types"]} >= {
        "Person",
        "Organization",
        "MartialArt",
        "Event",
        "Place",
        "Artifact",
    }
    knows = next(
        item for item in body["relation_types"] if item["id"] == "KNOWS"
    )
    assert knows["source_types"] == ["Person"]
    assert knows["target_types"] == ["MartialArt"]
    spouse = next(
        item for item in body["relation_types"] if item["id"] == "SPOUSE_OF"
    )
    assert spouse["source_types"] == ["Person"]
    assert spouse["target_types"] == ["Person"]
    assert spouse["symmetric"] is True
    assert body["example"] == {
        "subject": "令狐冲",
        "predicate": "KNOWS",
        "object": "独孤九剑",
    }
