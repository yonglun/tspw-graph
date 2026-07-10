from collections import defaultdict
from typing import Any

from app.graph.importer import GraphImporter, canonicalize_attribute_rows
from app.graph.models import GraphDocument, ImportSummary
from app.graph.neo4j import (
    CONSTRAINTS,
    INDEXES,
    RESOLVE_ATTRIBUTE_ENTITIES_QUERY,
    UPSERT_QUERIES,
    Neo4jGraphWriter,
)


class FakeGraph:
    def __init__(self, resolutions: dict[str, str] | None = None) -> None:
        self.records: dict[str, set[str]] = defaultdict(set)
        self.upsert_order: list[str] = []
        self.rows: dict[str, list[dict[str, Any]]] = {}
        self.resolutions = resolutions

    def ensure_constraints(self) -> None:
        return None

    def upsert_batch(self, label: str, rows: list[dict[str, Any]]) -> int:
        self.upsert_order.append(label)
        self.rows[label] = rows
        created = 0
        for row in rows:
            key = str(row["id"])
            if key not in self.records[label]:
                self.records[label].add(key)
                created += 1
        return created

    def resolve_attribute_entities(self, project_id, hints):
        if self.resolutions is not None:
            return self.resolutions
        entity_ids = self.records["Entity"]
        return {hint["id"]: hint["id"] for hint in hints if hint["id"] in entity_ids}

    def upsert_attribute_bundle(
        self, project_id, hints, attributes, evidence, protected_evidence_ids
    ):
        mappings = self.resolve_attribute_entities(project_id, hints)
        resolved = canonicalize_attribute_rows(project_id, attributes, mappings)
        attribute_evidence_ids = {
            evidence_id
            for attribute in resolved
            for evidence_id in attribute["evidence_ids"]
        }
        referenced = protected_evidence_ids | attribute_evidence_ids
        evidence_rows = [
            {"project_id": project_id, **row}
            for row in evidence
            if row["id"] in referenced
        ]
        created_evidence = self.upsert_batch("Evidence", evidence_rows)
        created_attributes = self.upsert_batch("AttributeAssertion", resolved)
        return ImportSummary(
            created_evidence=created_evidence,
            created_attributes=created_attributes,
            retained_attributes=len(resolved),
            retained_attribute_evidence=len(attribute_evidence_ids),
            retained_evidence=len(evidence_rows),
        )

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

    assert "MATCH (entity:Entity" in query
    assert "project_id: row.project_id" in query
    assert "entity.id = row.entity_id" in query
    assert "entity.type = row.entity_type" in query
    assert "coalesce(entity.review_status, 'ACCEPTED') <> 'MERGED'" in query
    assert "MERGE (assertion:AttributeAssertion" in query
    assert "id: row.id" in query
    assert "MERGE (entity)-[:HAS_ATTRIBUTE]->(assertion)" in query
    assert "MERGE (assertion)-[:EVIDENCED_BY]->(evidence)" in query
    assert "MERGE (entity:Entity" not in query
    assert "CREATE (entity" not in query


def test_attribute_backfill_drops_unresolved_assertions_and_orphan_evidence() -> None:
    document = sample_document().model_copy(
        update={"facts": [], "entities": sample_document().entities[:1]}
    )
    writer = FakeGraph(resolutions={})

    summary = GraphImporter(writer).import_attributes(document)

    assert writer.rows["AttributeAssertion"] == []
    assert writer.rows["Evidence"] == []
    assert summary.created_attributes == 0
    assert summary.created_evidence == 0
    assert summary.retained_attributes == 0
    assert summary.retained_attribute_evidence == 0


def test_attribute_backfill_drops_an_ambiguous_alias_without_fallback_choice() -> None:
    document = sample_document().model_copy(
        update={"facts": [], "entities": sample_document().entities[:1]}
    )
    writer = FakeGraph(resolutions={})

    GraphImporter(writer).import_attributes(document)

    assert writer.rows["AttributeAssertion"] == []
    assert writer.rows["Evidence"] == []


def test_attribute_backfill_rekeys_alias_assertion_to_canonical_entity() -> None:
    document = sample_document().model_copy(
        update={"facts": [], "entities": sample_document().entities[:1]}
    )
    canonical_id = "xiaoao:person:canonical-linghu"
    writer = FakeGraph(
        resolutions={"xiaoao:person:linghuchong": canonical_id}
    )

    GraphImporter(writer).import_attributes(document)

    row = writer.rows["AttributeAssertion"][0]
    assert row["entity_id"] == canonical_id
    assert row["id"] == "xiaoao:attribute:f2b76825428ac911"
    assert writer.rows["Evidence"][0]["id"] in row["evidence_ids"]


def test_canonical_and_alias_extractions_converge_to_one_assertion() -> None:
    base = sample_document()
    alias_attribute = base.attributes[0].model_copy(
        update={
            "id": "transient-alias-id",
            "entity_id": "xiaoao:person:alias-linghu",
            "entity_name": "令狐沖",
        }
    )
    document = base.model_copy(
        update={
            "facts": [],
            "entities": [
                base.entities[0],
                base.entities[0].model_copy(
                    update={"id": "xiaoao:person:alias-linghu", "name": "令狐沖"}
                ),
            ],
            "attributes": [base.attributes[0], alias_attribute],
        }
    )
    canonical_id = "xiaoao:person:canonical-linghu"
    writer = FakeGraph(
        resolutions={
            "xiaoao:person:linghuchong": canonical_id,
            "xiaoao:person:alias-linghu": canonical_id,
        }
    )

    summary = GraphImporter(writer).import_attributes(document)

    assert len(writer.rows["AttributeAssertion"]) == 1
    assert summary.created_attributes == 1
    assert summary.retained_attributes == 1


def test_entity_resolution_query_requires_unique_same_type_non_merged_fallback() -> None:
    query = " ".join(RESOLVE_ATTRIBUTE_ENTITIES_QUERY.split())
    assert "stable.type = hint.type" in query
    assert "coalesce(stable.review_status, 'ACCEPTED') <> 'MERGED'" in query
    assert "candidate.type = hint.type" in query
    assert "coalesce(candidate.review_status, 'ACCEPTED') <> 'MERGED'" in query
    assert "candidate.name = hint.name OR hint.name IN coalesce(candidate.aliases, [])" in query
    assert "size(candidates) = 1" in query
    assert "WHERE stable IS NULL" in query
    assert "SET entity.id = entity.id" in query


def test_attribute_bundle_resolves_locks_and_writes_in_one_transaction() -> None:
    class Counters:
        def __init__(self, nodes_created: int) -> None:
            self.nodes_created = nodes_created

    class Summary:
        def __init__(self, nodes_created: int) -> None:
            self.counters = Counters(nodes_created)

    class Result:
        def __init__(self, records=(), nodes_created=0) -> None:
            self.records = list(records)
            self.nodes_created = nodes_created

        def __iter__(self):
            return iter(self.records)

        def consume(self):
            return Summary(self.nodes_created)

    class Transaction:
        def __init__(self) -> None:
            self.statements: list[str] = []

        def run(self, statement, **parameters):
            self.statements.append(statement)
            if statement == RESOLVE_ATTRIBUTE_ENTITIES_QUERY:
                return Result([{"extracted_id": "alias", "canonical_id": "canonical"}])
            if statement == UPSERT_QUERIES["Evidence"]:
                return Result([{"evidence_id": "ev-1"}], nodes_created=1)
            if statement == UPSERT_QUERIES["AttributeAssertion"]:
                return Result(
                    [{"assertion_id": "canonical-assertion", "evidence_id": "ev-1"}],
                    nodes_created=1,
                )
            raise AssertionError("unexpected statement")

    class Session:
        def __init__(self) -> None:
            self.transaction = Transaction()
            self.execute_write_calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute_write(self, callback, *args):
            self.execute_write_calls += 1
            return callback(self.transaction, *args)

    class Driver:
        def __init__(self) -> None:
            self.fake_session = Session()

        def session(self):
            return self.fake_session

    driver = Driver()
    writer = Neo4jGraphWriter(driver)

    summary = writer.upsert_attribute_bundle(
        "p-1",
        [{"id": "alias", "name": "令狐冲", "type": "Person"}],
        [{
            "id": "transient",
            "entity_id": "alias",
            "entity_name": "令狐冲",
            "entity_type": "Person",
            "property_id": "identity",
            "value": "华山派大弟子",
            "value_type": "TEXT",
            "confidence": 1.0,
            "evidence_ids": ["ev-1"],
        }],
        [{
            "id": "ev-1",
            "chapter_id": "chapter-1",
            "start_offset": 0,
            "end_offset": 6,
            "quote": "华山派大弟子",
            "text_hash": "hash",
        }],
        set(),
    )

    assert driver.fake_session.execute_write_calls == 1
    assert driver.fake_session.transaction.statements == [
        RESOLVE_ATTRIBUTE_ENTITIES_QUERY,
        UPSERT_QUERIES["Evidence"],
        UPSERT_QUERIES["AttributeAssertion"],
    ]
    assert "SET entity.id = entity.id" in RESOLVE_ATTRIBUTE_ENTITIES_QUERY
    assert summary.created_attributes == 1
    assert summary.created_evidence == 1
    assert summary.retained_attributes == 1
    assert summary.retained_attribute_evidence == 1
    assert summary.retained_evidence == 1
