from fastapi.testclient import TestClient

from app.ontology.models import EntityType, EntityTypeDefinition, PropertyDefinition
from app.ontology.properties import (
    _resolve_property_definitions,
    property_definition_for,
    property_definitions_for,
)


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


def test_person_exposes_typed_property_definitions(client: TestClient) -> None:
    body = client.get("/api/ontology").json()
    person = next(item for item in body["entity_types"] if item["id"] == "Person")

    assert {item["id"] for item in person["effective_property_definitions"]} >= {
        "gender",
        "honorific",
        "identity",
        "life_status",
    }
    honorific = next(
        item
        for item in person["effective_property_definitions"]
        if item["id"] == "honorific"
    )
    gender = next(
        item
        for item in person["effective_property_definitions"]
        if item["id"] == "gender"
    )
    assert honorific["value_type"] == "TEXT"
    assert honorific["multiple"] is True
    assert gender["value_type"] == "ENUM"
    assert gender["enum_values"] == ["男", "女"]


def test_swordplay_inherits_martial_art_properties() -> None:
    ids = {item.id for item in property_definitions_for(EntityType.SWORDPLAY)}

    assert {"weapon_type", "characteristic", "prerequisite", "effect"} <= ids
    assert property_definition_for(EntityType.SWORDPLAY, "effect") is not None


def test_child_property_override_preserves_first_appearance_order() -> None:
    parent_property = PropertyDefinition(
        id="shared", label="父属性", description="父类型定义"
    )
    child_property = PropertyDefinition(
        id="shared", label="子属性", description="子类型覆盖定义"
    )
    child_only = PropertyDefinition(
        id="child_only", label="子类属性", description="仅由子类型定义"
    )
    definitions = (
        EntityTypeDefinition(
            id=EntityType.MARTIAL_ART,
            label="武学",
            description="武学",
            color="#000000",
            property_definitions=(parent_property,),
        ),
        EntityTypeDefinition(
            id=EntityType.SWORDPLAY,
            label="剑法",
            description="剑法",
            color="#111111",
            parent=EntityType.MARTIAL_ART,
            property_definitions=(child_property, child_only),
        ),
    )

    resolved = _resolve_property_definitions(EntityType.SWORDPLAY, definitions)

    assert [item.id for item in resolved] == ["shared", "child_only"]
    assert resolved[0].label == "子属性"
