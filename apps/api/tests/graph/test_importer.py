from collections import defaultdict
from typing import Any

from app.graph.importer import GraphImporter
from app.graph.models import GraphDocument
from app.graph.neo4j import CONSTRAINTS, INDEXES, UPSERT_QUERIES


class FakeGraph:
    def __init__(self) -> None:
        self.records: dict[str, set[str]] = defaultdict(set)
        self.upsert_order: list[str] = []

    def ensure_constraints(self) -> None:
        return None

    def upsert_batch(self, label: str, rows: list[dict[str, Any]]) -> int:
        self.upsert_order.append(label)
        created = 0
        for row in rows:
            key = str(row["id"])
            if key not in self.records[label]:
                self.records[label].add(key)
                created += 1
        return created

    def count(self, label: str) -> int:
        return len(self.records[label])


def sample_document() -> GraphDocument:
    return GraphDocument.model_validate(
        {
            "project": {"id": "xiaoao", "title": "笑傲江湖"},
            "chapters": [{"id": "xiaoao:chapter:1", "number": 1, "title": "灭门"}],
            "entities": [
                {"id": "xiaoao:person:linghuchong", "type": "Person", "name": "令狐冲", "aliases": []},
                {"id": "xiaoao:person:yuebuqun", "type": "Person", "name": "岳不群", "aliases": []},
                {"id": "xiaoao:sect:huashan", "type": "Sect", "name": "华山派", "aliases": []},
            ],
            "facts": [
                {"id": "xiaoao:fact:master", "type": "MASTER_OF", "source_id": "xiaoao:person:yuebuqun", "target_id": "xiaoao:person:linghuchong", "evidence_ids": ["xiaoao:evidence:1"]},
                {"id": "xiaoao:fact:member", "type": "MEMBER_OF", "source_id": "xiaoao:person:linghuchong", "target_id": "xiaoao:sect:huashan", "evidence_ids": ["xiaoao:evidence:2"]},
            ],
            "evidence": [
                {"id": "xiaoao:evidence:1", "chapter_id": "xiaoao:chapter:1", "start_offset": 0, "end_offset": 3, "quote": "令狐冲", "text_hash": "hash-1"},
                {"id": "xiaoao:evidence:2", "chapter_id": "xiaoao:chapter:1", "start_offset": 4, "end_offset": 7, "quote": "华山派", "text_hash": "hash-2"},
            ],
            "attributes": [
                {
                    "id": "xiaoao:attribute:linghuchong-level",
                    "entity_id": "xiaoao:person:linghuchong",
                    "entity_name": "令狐冲",
                    "entity_type": "Person",
                    "property_id": "martial_arts_level",
                    "value": "高手",
                    "value_type": "TEXT",
                    "confidence": 0.9,
                    "evidence_ids": ["xiaoao:evidence:1"],
                }
            ],
        }
    )


def test_importing_same_document_twice_is_idempotent() -> None:
    fake_graph = FakeGraph()
    importer = GraphImporter(fake_graph)

    first = importer.import_document(sample_document())
    second = importer.import_document(sample_document())

    assert first.created_entities == 3
    assert first.created_facts == 2
    assert first.created_evidence == 2
    assert first.created_attributes == 1
    assert second.created_entities == 0
    assert second.created_facts == 0
    assert second.created_evidence == 0
    assert second.created_attributes == 0
    assert fake_graph.count("Entity") == 3
    assert fake_graph.count("Fact") == 2
    assert fake_graph.count("Evidence") == 2
    assert fake_graph.count("AttributeAssertion") == 1
    assert fake_graph.upsert_order[:6] == [
        "Project",
        "Chapter",
        "Entity",
        "Evidence",
        "AttributeAssertion",
        "Fact",
    ]


def test_attribute_schema_statements_are_idempotent() -> None:
    assert (
        "CREATE CONSTRAINT attribute_assertion_id IF NOT EXISTS "
        "FOR (n:AttributeAssertion) REQUIRE (n.project_id, n.id) IS UNIQUE"
    ) in CONSTRAINTS
    assert (
        "CREATE INDEX entity_project_name IF NOT EXISTS "
        "FOR (n:Entity) ON (n.project_id, n.name)"
    ) in INDEXES
    assert (
        "CREATE INDEX entity_project_type IF NOT EXISTS "
        "FOR (n:Entity) ON (n.project_id, n.type)"
    ) in INDEXES


def test_attribute_upsert_matches_existing_entity_without_creating_one() -> None:
    query = " ".join(UPSERT_QUERIES["AttributeAssertion"].split())

    assert "OPTIONAL MATCH (stable:Entity" in query
    assert "project_id: row.project_id" in query
    assert "id: row.entity_id" in query
    assert "OPTIONAL MATCH (candidate:Entity {project_id: row.project_id})" in query
    assert "stable.type = row.entity_type" in query
    assert "coalesce(stable.review_status, 'ACCEPTED') <> 'MERGED'" in query
    assert "candidate.type = row.entity_type" in query
    assert "coalesce(candidate.review_status, 'ACCEPTED') <> 'MERGED'" in query
    assert (
        "candidate.name = row.entity_name OR "
        "row.entity_name IN coalesce(candidate.aliases, [])"
    ) in query
    assert "coalesce(stable, fallback) AS entity" in query
    assert "WHERE entity IS NOT NULL" in query
    assert "MERGE (assertion:AttributeAssertion" in query
    assert "id: row.id" in query
    assert "MERGE (entity)-[:HAS_ATTRIBUTE]->(assertion)" in query
    assert "MERGE (assertion)-[:EVIDENCED_BY]->(evidence)" in query
    assert "MERGE (entity:Entity" not in query
    assert "CREATE (entity" not in query
