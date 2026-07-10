from collections.abc import Sequence
from typing import Any

from neo4j import Driver, GraphDatabase

from app.graph.importer import canonicalize_attribute_rows
from app.graph.models import ImportSummary
from app.settings import Settings


CONSTRAINTS = (
    "CREATE CONSTRAINT project_id IF NOT EXISTS FOR (n:Project) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT chapter_id IF NOT EXISTS FOR (n:Chapter) REQUIRE (n.project_id, n.id) IS UNIQUE",
    "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE (n.project_id, n.id) IS UNIQUE",
    "CREATE CONSTRAINT fact_id IF NOT EXISTS FOR (n:Fact) REQUIRE (n.project_id, n.id) IS UNIQUE",
    "CREATE CONSTRAINT evidence_id IF NOT EXISTS FOR (n:Evidence) REQUIRE (n.project_id, n.id) IS UNIQUE",
    "CREATE CONSTRAINT attribute_assertion_id IF NOT EXISTS FOR (n:AttributeAssertion) REQUIRE (n.project_id, n.id) IS UNIQUE",
)

INDEXES = (
    "CREATE INDEX entity_project_name IF NOT EXISTS FOR (n:Entity) ON (n.project_id, n.name)",
    "CREATE INDEX entity_project_type IF NOT EXISTS FOR (n:Entity) ON (n.project_id, n.type)",
)


RESOLVE_ATTRIBUTE_ENTITIES_QUERY = """
    UNWIND $hints AS hint
    OPTIONAL MATCH (stable:Entity {
        project_id: $project_id,
        id: hint.id
    })
    WHERE stable.type = hint.type
      AND coalesce(stable.review_status, 'ACCEPTED') <> 'MERGED'
    WITH hint, stable
    CALL {
        WITH hint, stable
        OPTIONAL MATCH (candidate:Entity {project_id: $project_id})
        WHERE stable IS NULL
          AND candidate.type = hint.type
          AND coalesce(candidate.review_status, 'ACCEPTED') <> 'MERGED'
          AND (
            candidate.name = hint.name
            OR hint.name IN coalesce(candidate.aliases, [])
          )
        RETURN collect(candidate) AS candidates
    }
    WITH hint,
         CASE
           WHEN stable IS NOT NULL THEN stable
           WHEN size(candidates) = 1 THEN candidates[0]
           ELSE NULL
         END AS entity
    WHERE entity IS NOT NULL
    SET entity.id = entity.id
    RETURN hint.id AS extracted_id,
           entity.id AS canonical_id
"""


UPSERT_QUERIES: dict[str, str] = {
    "Project": """
        UNWIND $rows AS row
        MERGE (n:Project {id: row.id})
        SET n += row
    """,
    "Chapter": """
        UNWIND $rows AS row
        MATCH (p:Project {id: row.project_id})
        MERGE (n:Chapter {project_id: row.project_id, id: row.id})
        SET n += row
        MERGE (p)-[:HAS_CHAPTER]->(n)
    """,
    "Entity": """
        UNWIND $rows AS row
        MATCH (p:Project {id: row.project_id})
        MERGE (n:Entity {project_id: row.project_id, id: row.id})
        SET n += row
        MERGE (p)-[:HAS_ENTITY]->(n)
    """,
    "Evidence": """
        UNWIND $rows AS row
        MATCH (c:Chapter {project_id: row.project_id, id: row.chapter_id})
        MERGE (n:Evidence {project_id: row.project_id, id: row.id})
        SET n += row
        MERGE (n)-[:IN_CHAPTER]->(c)
        RETURN n.id AS evidence_id
    """,
    "AttributeAssertion": """
        UNWIND $rows AS row
        MATCH (entity:Entity {project_id: row.project_id})
        WHERE entity.id = row.entity_id
          AND entity.type = row.entity_type
          AND coalesce(entity.review_status, 'ACCEPTED') <> 'MERGED'
          AND all(evidence_id IN row.evidence_ids WHERE EXISTS {
            MATCH (:Evidence {
                project_id: row.project_id,
                id: evidence_id
            })
          })
        MERGE (assertion:AttributeAssertion {
            project_id: row.project_id,
            id: row.id
        })
        SET assertion += row
        MERGE (entity)-[:HAS_ATTRIBUTE]->(assertion)
        WITH assertion, row
        UNWIND row.evidence_ids AS evidence_id
        MATCH (evidence:Evidence {
            project_id: row.project_id,
            id: evidence_id
        })
        MERGE (assertion)-[:EVIDENCED_BY]->(evidence)
        RETURN assertion.id AS assertion_id, evidence.id AS evidence_id
    """,
    "Fact": """
        UNWIND $rows AS row
        MATCH (s:Entity {project_id: row.project_id, id: row.source_id})
        MATCH (t:Entity {project_id: row.project_id, id: row.target_id})
        MERGE (n:Fact {project_id: row.project_id, id: row.id})
        SET n += row
        MERGE (n)-[:SOURCE]->(s)
        MERGE (n)-[:TARGET]->(t)
        MERGE (s)-[r:RELATED {project_id: row.project_id, id: row.id}]->(t)
        SET r.type = row.type,
            r.from_chapter = row.from_chapter,
            r.to_chapter = row.to_chapter,
            r.confidence = row.confidence
        WITH n, row
        UNWIND row.evidence_ids AS evidence_id
        MATCH (e:Evidence {project_id: row.project_id, id: evidence_id})
        MERGE (n)-[:EVIDENCED_BY]->(e)
    """,
}


class Neo4jGraphWriter:
    def __init__(self, driver: Driver, batch_size: int = 500) -> None:
        self.driver = driver
        self.batch_size = batch_size

    @classmethod
    def from_settings(cls, settings: Settings) -> "Neo4jGraphWriter":
        driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        return cls(driver)

    def close(self) -> None:
        self.driver.close()

    def ensure_constraints(self) -> None:
        with self.driver.session() as session:
            for statement in CONSTRAINTS:
                session.run(statement).consume()
            for statement in INDEXES:
                session.run(statement).consume()

    def delete_project(self, project_id: str) -> None:
        with self.driver.session() as session:
            session.run(
                "MATCH (n {project_id: $project_id}) DETACH DELETE n",
                project_id=project_id,
            ).consume()
            session.run(
                "MATCH (p:Project {id: $project_id}) DETACH DELETE p",
                project_id=project_id,
            ).consume()

    def upsert_batch(self, label: str, rows: list[dict[str, Any]]) -> int:
        if label not in UPSERT_QUERIES:
            raise ValueError(f"unsupported graph label: {label}")
        created = 0
        with self.driver.session() as session:
            for batch in self._batches(rows):
                summary = session.run(UPSERT_QUERIES[label], rows=batch).consume()
                created += summary.counters.nodes_created
        return created

    def resolve_attribute_entities(
        self, project_id: str, hints: list[dict[str, str]]
    ) -> dict[str, str]:
        if not hints:
            return {}
        with self.driver.session() as session:
            return {
                record["extracted_id"]: record["canonical_id"]
                for record in session.run(
                    RESOLVE_ATTRIBUTE_ENTITIES_QUERY,
                    project_id=project_id,
                    hints=hints,
                )
            }

    def upsert_attribute_bundle(
        self,
        project_id: str,
        hints: list[dict[str, str]],
        attributes: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        protected_evidence_ids: set[str],
    ) -> ImportSummary:
        with self.driver.session() as session:
            return session.execute_write(
                self._upsert_attribute_bundle_tx,
                project_id,
                hints,
                attributes,
                evidence,
                protected_evidence_ids,
            )

    def _upsert_attribute_bundle_tx(
        self,
        transaction: Any,
        project_id: str,
        hints: list[dict[str, str]],
        attributes: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        protected_evidence_ids: set[str],
    ) -> ImportSummary:
        mappings = (
            {
                record["extracted_id"]: record["canonical_id"]
                for record in transaction.run(
                    RESOLVE_ATTRIBUTE_ENTITIES_QUERY,
                    project_id=project_id,
                    hints=hints,
                )
            }
            if hints
            else {}
        )
        resolved_attributes = canonicalize_attribute_rows(
            project_id, attributes, mappings
        )
        attribute_evidence_ids = {
            evidence_id
            for attribute in resolved_attributes
            for evidence_id in attribute["evidence_ids"]
        }
        referenced_evidence_ids = protected_evidence_ids | attribute_evidence_ids
        evidence_rows = [
            {"project_id": project_id, **row}
            for row in evidence
            if row["id"] in referenced_evidence_ids
        ]

        created_evidence = 0
        retained_evidence_ids: set[str] = set()
        for batch in self._batches(evidence_rows):
            result = transaction.run(UPSERT_QUERIES["Evidence"], rows=batch)
            retained_evidence_ids.update(
                record["evidence_id"] for record in result
            )
            created_evidence += result.consume().counters.nodes_created

        created_attributes = 0
        retained_attribute_ids: set[str] = set()
        retained_attribute_evidence_ids: set[str] = set()
        for batch in self._batches(resolved_attributes):
            result = transaction.run(
                UPSERT_QUERIES["AttributeAssertion"], rows=batch
            )
            for record in result:
                retained_attribute_ids.add(record["assertion_id"])
                retained_attribute_evidence_ids.add(record["evidence_id"])
            created_attributes += result.consume().counters.nodes_created

        return ImportSummary(
            created_evidence=created_evidence,
            created_attributes=created_attributes,
            retained_attributes=len(retained_attribute_ids),
            retained_attribute_evidence=len(retained_attribute_evidence_ids),
            retained_evidence=len(retained_evidence_ids),
        )

    def _batches(
        self, rows: Sequence[dict[str, Any]]
    ) -> list[list[dict[str, Any]]]:
        return [
            list(rows[index : index + self.batch_size])
            for index in range(0, len(rows), self.batch_size)
        ]
