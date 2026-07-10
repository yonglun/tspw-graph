from typing import Any, Protocol

from neo4j import Driver, GraphDatabase

from app.settings import Settings


class GraphRepository(Protocol):
    def search_exact(
        self, project_id: str, query: str, types: list[str], limit: int
    ) -> list[dict[str, Any]]: ...

    def search_contains(
        self, project_id: str, query: str, types: list[str], limit: int
    ) -> list[dict[str, Any]]: ...

    def search(
        self, project_id: str, query: str, types: list[str], limit: int
    ) -> list[dict[str, Any]]: ...


class Neo4jGraphRepository:
    def __init__(self, driver: Driver) -> None:
        self.driver = driver

    @classmethod
    def from_settings(cls, settings: Settings) -> "Neo4jGraphRepository":
        return cls(
            GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            )
        )

    def close(self) -> None:
        self.driver.close()

    def search(
        self, project_id: str, query: str, types: list[str], limit: int
    ) -> list[dict[str, Any]]:
        exact = self.search_exact(project_id, query, types, limit)
        if len(exact) >= limit:
            return exact[:limit]
        contains = self.search_contains(
            project_id, query, types, limit - len(exact)
        )
        unique = {row["id"]: row for row in exact}
        for row in contains:
            unique.setdefault(row["id"], row)
        return list(unique.values())[:limit]

    def search_exact(
        self, project_id: str, query: str, types: list[str], limit: int
    ) -> list[dict[str, Any]]:
        statement = """
            MATCH (n:Entity)
            WHERE n.project_id = $project_id AND n.name = $search_text
              AND (size($types) = 0 OR n.type IN $types)
              AND coalesce(n.review_status, 'ACCEPTED') <> 'MERGED'
            RETURN properties(n) AS entity
            ORDER BY n.id
            LIMIT $limit
        """
        return self._entities(
            statement,
            project_id=project_id,
            search_text=query,
            types=types,
            limit=limit,
        )

    def search_contains(
        self, project_id: str, query: str, types: list[str], limit: int
    ) -> list[dict[str, Any]]:
        statement = """
            MATCH (n:Entity {project_id: $project_id})
            WHERE (toLower(n.name) CONTAINS toLower($search_text)
                OR any(alias IN coalesce(n.aliases, []) WHERE toLower(alias) CONTAINS toLower($search_text)))
              AND n.name <> $search_text
              AND (size($types) = 0 OR n.type IN $types)
              AND coalesce(n.review_status, 'ACCEPTED') <> 'MERGED'
            RETURN properties(n) AS entity
            ORDER BY n.name, n.id
            LIMIT $limit
        """
        return self._entities(
            statement,
            project_id=project_id,
            search_text=query,
            types=types,
            limit=limit,
        )

    def neighborhood(
        self,
        project_id: str,
        entity_id: str,
        depth: int,
        limit: int,
        from_chapter: int | None,
        to_chapter: int | None,
    ) -> dict[str, list[dict[str, Any]]] | None:
        if depth == 1:
            statement = """
                MATCH (center:Entity {project_id: $project_id, id: $entity_id})
                WHERE coalesce(center.review_status, 'ACCEPTED') <> 'MERGED'
                OPTIONAL MATCH (center)-[edge:RELATED]-(other:Entity {project_id: $project_id})
                WHERE coalesce(edge.review_status, 'ACCEPTED') <> 'REJECTED'
                  AND ($from_chapter IS NULL OR edge.to_chapter IS NULL OR edge.to_chapter >= $from_chapter)
                  AND ($to_chapter IS NULL OR edge.from_chapter IS NULL OR edge.from_chapter <= $to_chapter)
                  AND coalesce(other.review_status, 'ACCEPTED') <> 'MERGED'
                WITH center, edge, other
                ORDER BY edge.id
                WITH center, collect(edge)[..$limit] AS edges,
                    collect(other)[..$limit] AS others
                RETURN [center] + others AS nodes, edges
            """
        elif depth == 2:
            statement = """
            MATCH p=(center:Entity {project_id: $project_id, id: $entity_id})
                -[rels:RELATED*1..2]-(other:Entity {project_id: $project_id})
            WHERE all(r IN rels WHERE
                coalesce(r.review_status, 'ACCEPTED') <> 'REJECTED'
                AND ($from_chapter IS NULL OR r.to_chapter IS NULL OR r.to_chapter >= $from_chapter)
                AND ($to_chapter IS NULL OR r.from_chapter IS NULL OR r.from_chapter <= $to_chapter))
              AND coalesce(center.review_status, 'ACCEPTED') <> 'MERGED'
              AND coalesce(other.review_status, 'ACCEPTED') <> 'MERGED'
            WITH collect(p)[..$limit] AS paths
            RETURN
                reduce(ns = [], p IN paths | ns + nodes(p)) AS nodes,
                reduce(rs = [], p IN paths | rs + relationships(p)) AS edges
            """
        else:
            raise ValueError("depth must be 1 or 2")
        with self.driver.session() as session:
            record = session.run(
                statement,
                project_id=project_id,
                entity_id=entity_id,
                limit=limit,
                from_chapter=from_chapter,
                to_chapter=to_chapter,
            ).single()
            if record is None:
                return None
            nodes = {node["id"]: dict(node) for node in record["nodes"]}
            edges = {
                edge["id"]: {
                    **dict(edge),
                    "source_id": edge.start_node["id"],
                    "target_id": edge.end_node["id"],
                }
                for edge in record["edges"]
            }
            return {"nodes": list(nodes.values()), "edges": list(edges.values())}

    def shortest_path(
        self, project_id: str, source_id: str, target_id: str, max_depth: int
    ) -> dict[str, list[dict[str, Any]]]:
        statement = f"""
            MATCH (source:Entity {{project_id: $project_id, id: $source_id}}),
                  (target:Entity {{project_id: $project_id, id: $target_id}})
            MATCH p=shortestPath((source)-[:RELATED*..{max_depth}]-(target))
            WHERE coalesce(source.review_status, 'ACCEPTED') <> 'MERGED'
              AND coalesce(target.review_status, 'ACCEPTED') <> 'MERGED'
              AND all(r IN relationships(p) WHERE coalesce(r.review_status, 'ACCEPTED') <> 'REJECTED')
              AND all(n IN nodes(p) WHERE coalesce(n.review_status, 'ACCEPTED') <> 'MERGED')
            RETURN nodes(p) AS nodes, relationships(p) AS edges
        """
        with self.driver.session() as session:
            record = session.run(
                statement,
                project_id=project_id,
                source_id=source_id,
                target_id=target_id,
            ).single()
            if record is None:
                return {"nodes": [], "edges": []}
            return {
                "nodes": [dict(node) for node in record["nodes"]],
                "edges": [
                    {
                        **dict(edge),
                        "source_id": edge.start_node["id"],
                        "target_id": edge.end_node["id"],
                    }
                    for edge in record["edges"]
                ],
            }

    def entity_detail(self, project_id: str, entity_id: str) -> dict[str, Any] | None:
        statement = """
            MATCH (entity:Entity {project_id: $project_id, id: $entity_id})
            WHERE coalesce(entity.review_status, 'ACCEPTED') <> 'MERGED'
            CALL {
                WITH entity
                OPTIONAL MATCH (entity)-[:HAS_ATTRIBUTE]->(attribute:AttributeAssertion)
                OPTIONAL MATCH (attribute)-[:EVIDENCED_BY]->(attribute_evidence:Evidence)
                    -[:IN_CHAPTER]->(attribute_chapter:Chapter)
                WITH attribute, collect(DISTINCT {
                    id: attribute_evidence.id,
                    chapter_id: attribute_chapter.id,
                    chapter_number: attribute_chapter.number,
                    chapter_title: attribute_chapter.title,
                    start_offset: attribute_evidence.start_offset,
                    end_offset: attribute_evidence.end_offset,
                    quote: attribute_evidence.quote
                }) AS evidence_rows
                WITH attribute,
                    [item IN evidence_rows WHERE item.id IS NOT NULL] AS evidence
                WHERE attribute IS NOT NULL
                RETURN collect({
                    id: attribute.id,
                    property_id: attribute.property_id,
                    value_type: attribute.value_type,
                    value: attribute.value,
                    confidence: coalesce(attribute.confidence, 1.0),
                    evidence: evidence
                }) AS attributes
            }
            CALL {
                WITH entity
                OPTIONAL MATCH (fact:Fact)-[:SOURCE|TARGET]->(entity)
                WHERE coalesce(fact.review_status, 'ACCEPTED') <> 'REJECTED'
                OPTIONAL MATCH (fact)-[:SOURCE]->(source:Entity)
                OPTIONAL MATCH (fact)-[:TARGET]->(target:Entity)
                OPTIONAL MATCH (fact)-[:EVIDENCED_BY]->(evidence:Evidence)
                    -[:IN_CHAPTER]->(chapter:Chapter)
                WITH fact, source, target, evidence, chapter
                WHERE fact IS NOT NULL
                  AND coalesce(source.review_status, 'ACCEPTED') <> 'MERGED'
                  AND coalesce(target.review_status, 'ACCEPTED') <> 'MERGED'
                RETURN collect(DISTINCT {
                    id: fact.id,
                    type: fact.type,
                    source_id: source.id,
                    target_id: target.id,
                    review_status: fact.review_status,
                    source: {id: source.id, type: source.type, name: source.name},
                    target: {id: target.id, type: target.type, name: target.name},
                    evidence: {
                        id: evidence.id,
                        chapter_id: chapter.id,
                        chapter_number: chapter.number,
                        chapter_title: chapter.title,
                        start_offset: evidence.start_offset,
                        end_offset: evidence.end_offset,
                        quote: evidence.quote
                    }
                }) AS rows
            }
            RETURN properties(entity) AS entity, attributes, rows
        """
        with self.driver.session() as session:
            record = session.run(statement, project_id=project_id, entity_id=entity_id).single()
            if record is None:
                return None
            return {
                "entity": record["entity"],
                "attributes": record["attributes"],
                "rows": record["rows"],
            }

    def timeline(
        self,
        project_id: str,
        person_id: str | None,
        from_chapter: int | None,
        to_chapter: int | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        statement = """
            MATCH (event:Entity {project_id: $project_id})-[r:RELATED]-(person:Entity {project_id: $project_id})
            WHERE event.type IN ['Event', 'TeachingEvent']
              AND coalesce(event.review_status, 'ACCEPTED') <> 'MERGED'
              AND coalesce(person.review_status, 'ACCEPTED') <> 'MERGED'
              AND coalesce(r.review_status, 'ACCEPTED') <> 'REJECTED'
              AND ($person_id IS NULL OR person.id = $person_id)
              AND ($from_chapter IS NULL OR r.from_chapter >= $from_chapter)
              AND ($to_chapter IS NULL OR r.from_chapter <= $to_chapter)
            RETURN DISTINCT properties(event) AS event, min(r.from_chapter) AS chapter_number
            ORDER BY chapter_number, event.name
            LIMIT $limit
        """
        with self.driver.session() as session:
            return [
                {"event": record["event"], "chapter_number": record["chapter_number"]}
                for record in session.run(
                    statement,
                    project_id=project_id,
                    person_id=person_id,
                    from_chapter=from_chapter,
                    to_chapter=to_chapter,
                    limit=limit,
                )
            ]

    def entity_exists(self, project_id: str, entity_id: str) -> bool:
        with self.driver.session() as session:
            return session.run(
                """
                MATCH (n:Entity {project_id: $project_id, id: $entity_id})
                WHERE coalesce(n.review_status, 'ACCEPTED') <> 'MERGED'
                RETURN count(n) > 0 AS found
                """,
                project_id=project_id,
                entity_id=entity_id,
            ).single()["found"]

    def _entities(self, statement: str, **parameters: Any) -> list[dict[str, Any]]:
        with self.driver.session() as session:
            return [dict(record["entity"]) for record in session.run(statement, **parameters)]
