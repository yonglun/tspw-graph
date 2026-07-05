from collections.abc import Sequence
from typing import Any

from neo4j import Driver, GraphDatabase

from app.settings import Settings


CONSTRAINTS = (
    "CREATE CONSTRAINT project_id IF NOT EXISTS FOR (n:Project) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT chapter_id IF NOT EXISTS FOR (n:Chapter) REQUIRE (n.project_id, n.id) IS UNIQUE",
    "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE (n.project_id, n.id) IS UNIQUE",
    "CREATE CONSTRAINT fact_id IF NOT EXISTS FOR (n:Fact) REQUIRE (n.project_id, n.id) IS UNIQUE",
    "CREATE CONSTRAINT evidence_id IF NOT EXISTS FOR (n:Evidence) REQUIRE (n.project_id, n.id) IS UNIQUE",
)


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
    """,
    "Fact": """
        UNWIND $rows AS row
        MATCH (s:Entity {project_id: row.project_id, id: row.source_id})
        MATCH (t:Entity {project_id: row.project_id, id: row.target_id})
        MERGE (n:Fact {project_id: row.project_id, id: row.id})
        SET n += row
        MERGE (n)-[:SOURCE]->(s)
        MERGE (n)-[:TARGET]->(t)
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

    def upsert_batch(self, label: str, rows: list[dict[str, Any]]) -> int:
        if label not in UPSERT_QUERIES:
            raise ValueError(f"unsupported graph label: {label}")
        created = 0
        with self.driver.session() as session:
            for batch in self._batches(rows):
                summary = session.run(UPSERT_QUERIES[label], rows=batch).consume()
                created += summary.counters.nodes_created
        return created

    def _batches(
        self, rows: Sequence[dict[str, Any]]
    ) -> list[list[dict[str, Any]]]:
        return [
            list(rows[index : index + self.batch_size])
            for index in range(0, len(rows), self.batch_size)
        ]
