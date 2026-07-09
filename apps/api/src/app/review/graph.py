from dataclasses import dataclass
from typing import Any

from neo4j import Driver, GraphDatabase

from app.review.rules import FactCandidate
from app.settings import Settings


@dataclass(frozen=True)
class ReviewGraphSnapshot:
    facts: list[FactCandidate]
    entities: list[dict[str, Any]]


class ReviewGraphRepository:
    def __init__(self, driver: Driver) -> None:
        self.driver = driver

    @classmethod
    def from_settings(cls, settings: Settings) -> "ReviewGraphRepository":
        return cls(
            GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            )
        )

    def close(self) -> None:
        self.driver.close()

    def accept_fact(self, project_id: str, fact_id: str) -> None:
        self._run(
            """
            MATCH (fact:Fact {project_id: $project_id, id: $fact_id})
            SET fact.review_status = 'ACCEPTED'
            WITH fact
            OPTIONAL MATCH ()-[related:RELATED {project_id: $project_id, id: $fact_id}]->()
            SET related.review_status = 'ACCEPTED'
            """,
            project_id=project_id,
            fact_id=fact_id,
        )

    def reject_fact(self, project_id: str, fact_id: str) -> None:
        self._run(
            """
            MATCH (fact:Fact {project_id: $project_id, id: $fact_id})
            SET fact.review_status = 'REJECTED'
            WITH fact
            OPTIONAL MATCH ()-[related:RELATED {project_id: $project_id, id: $fact_id}]->()
            SET related.review_status = 'REJECTED'
            """,
            project_id=project_id,
            fact_id=fact_id,
        )

    def merge_entities(
        self, project_id: str, source_entity_id: str, target_entity_id: str
    ) -> None:
        self._run(
            """
            MATCH (source:Entity {project_id: $project_id, id: $source_entity_id})
            MATCH (target:Entity {project_id: $project_id, id: $target_entity_id})
            WITH source, target,
                [alias IN coalesce(target.aliases, []) + coalesce(source.aliases, []) + [source.name]
                    WHERE alias IS NOT NULL AND alias <> '' AND alias <> target.name] AS aliases
            SET target.review_status = coalesce(target.review_status, 'ACCEPTED'),
                target.aliases = reduce(unique_aliases = [], alias IN aliases |
                    CASE
                        WHEN alias IN unique_aliases THEN unique_aliases
                        ELSE unique_aliases + alias
                    END
                )

            WITH source, target
            CALL {
                WITH source, target
                MATCH (source)-[related:RELATED {project_id: $project_id}]->(other:Entity {project_id: $project_id})
                WHERE other.id <> target.id
                MERGE (target)-[migrated:RELATED {project_id: related.project_id, id: related.id}]->(other)
                SET migrated += properties(related)
                DELETE related
                RETURN count(*) AS outgoing_count
            }
            CALL {
                WITH source, target
                MATCH (other:Entity {project_id: $project_id})-[related:RELATED {project_id: $project_id}]->(source)
                WHERE other.id <> target.id
                MERGE (other)-[migrated:RELATED {project_id: related.project_id, id: related.id}]->(target)
                SET migrated += properties(related)
                DELETE related
                RETURN count(*) AS incoming_count
            }
            CALL {
                WITH source, target
                MATCH (fact:Fact {project_id: $project_id})
                WHERE fact.source_id = source.id OR fact.target_id = source.id
                OPTIONAL MATCH (fact)-[old_ref:SOURCE|TARGET]->(source)
                DELETE old_ref
                SET fact.source_id = CASE WHEN fact.source_id = source.id THEN target.id ELSE fact.source_id END,
                    fact.target_id = CASE WHEN fact.target_id = source.id THEN target.id ELSE fact.target_id END,
                    fact.review_status = coalesce(fact.review_status, 'ACCEPTED')
                WITH fact, target
                FOREACH (_ IN CASE WHEN fact.source_id = target.id THEN [1] ELSE [] END |
                    MERGE (fact)-[:SOURCE]->(target)
                )
                FOREACH (_ IN CASE WHEN fact.target_id = target.id THEN [1] ELSE [] END |
                    MERGE (fact)-[:TARGET]->(target)
                )
                RETURN count(fact) AS fact_count
            }
            DETACH DELETE source
            """,
            project_id=project_id,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
        )

    def split_alias(
        self,
        project_id: str,
        source_entity_id: str,
        alias: str,
        target_entity_id: str | None,
    ) -> str:
        target_id = target_entity_id or f"{source_entity_id}__alias__{alias}"
        self._run(
            """
            MATCH (source:Entity {project_id: $project_id, id: $source_entity_id})
            SET source.aliases = [a IN coalesce(source.aliases, []) WHERE a <> $alias],
                source.review_status = 'SPLIT_SOURCE'
            MERGE (target:Entity {project_id: $project_id, id: $target_id})
            ON CREATE SET target.name = $alias,
                target.type = source.type,
                target.aliases = [],
                target.description = '',
                target.review_status = 'ACCEPTED'
            ON MATCH SET target.review_status = coalesce(target.review_status, 'ACCEPTED')
            """,
            project_id=project_id,
            source_entity_id=source_entity_id,
            alias=alias,
            target_id=target_id,
        )
        return target_id

    def review_candidates(self, project_id: str) -> ReviewGraphSnapshot:
        statement = """
            MATCH (fact:Fact {project_id: $project_id})
            OPTIONAL MATCH (fact)-[:SOURCE]->(source:Entity)
            OPTIONAL MATCH (fact)-[:TARGET]->(target:Entity)
            OPTIONAL MATCH (fact)-[:EVIDENCED_BY]->(evidence:Evidence)
            WITH fact, source, target, collect(evidence.id) AS evidence_ids
            RETURN collect({
                id: fact.id, type: fact.type, source_id: source.id, target_id: target.id,
                confidence: coalesce(fact.confidence, 1.0), evidence_ids: evidence_ids,
                source_type: source.type, target_type: target.type
            }) AS facts
        """
        with self.driver.session() as session:
            record = session.run(statement, project_id=project_id).single()
            fact_rows = record["facts"] if record else []
            entity_rows = session.run(
                """
                MATCH (entity:Entity {project_id: $project_id})
                RETURN properties(entity) AS entity
                """,
                project_id=project_id,
            )
            return ReviewGraphSnapshot(
                facts=[FactCandidate(**row) for row in fact_rows if row["id"]],
                entities=[dict(row["entity"]) for row in entity_rows],
            )

    def _run(self, statement: str, **parameters: Any) -> None:
        with self.driver.session() as session:
            session.run(statement, **parameters).consume()
