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

    def relation_detail(
        self, project_id: str, relation_id: str
    ) -> dict[str, Any] | None: ...

    def timeline_detail(
        self, project_id: str, event_id: str
    ) -> dict[str, Any] | None: ...


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
                CALL {
                    WITH center
                    OPTIONAL MATCH (center)-[edge:RELATED]-(other:Entity {project_id: $project_id})
                    WHERE coalesce(edge.review_status, 'ACCEPTED') <> 'REJECTED'
                      AND ($from_chapter IS NULL OR edge.to_chapter IS NULL OR edge.to_chapter >= $from_chapter)
                      AND ($to_chapter IS NULL OR edge.from_chapter IS NULL OR edge.from_chapter <= $to_chapter)
                      AND coalesce(other.review_status, 'ACCEPTED') <> 'MERGED'
                    WITH edge, other
                    ORDER BY edge.id, other.id
                    LIMIT $limit
                    RETURN collect(edge) AS edges, collect(other) AS others
                }
                RETURN [center] + others AS nodes, edges
            """
        elif depth == 2:
            statement = """
                MATCH (center:Entity {project_id: $project_id, id: $entity_id})
                WHERE coalesce(center.review_status, 'ACCEPTED') <> 'MERGED'
                CALL {
                    WITH center
                    OPTIONAL MATCH path=(center)-[rels:RELATED*1..2]-(other:Entity {project_id: $project_id})
                    WHERE all(r IN rels WHERE
                        coalesce(r.review_status, 'ACCEPTED') <> 'REJECTED'
                        AND ($from_chapter IS NULL OR r.to_chapter IS NULL OR r.to_chapter >= $from_chapter)
                        AND ($to_chapter IS NULL OR r.from_chapter IS NULL OR r.from_chapter <= $to_chapter))
                      AND coalesce(other.review_status, 'ACCEPTED') <> 'MERGED'
                    WITH path, rels, other
                    ORDER BY length(path), other.id,
                        reduce(key = '', relation IN rels | key + '|' + relation.id)
                    LIMIT $limit
                    RETURN collect(path) AS paths
                }
                RETURN
                    [center] + reduce(ns = [], path IN paths | ns + nodes(path)) AS nodes,
                    reduce(rs = [], path IN paths | rs + relationships(path)) AS edges
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
            return self._bounded_neighborhood(record["nodes"], record["edges"], limit)

    @staticmethod
    def _bounded_neighborhood(nodes, edges, limit: int) -> dict[str, list[dict[str, Any]]]:
        retained_nodes: dict[str, dict[str, Any]] = {}
        for node in nodes:
            node_id = node["id"]
            if node_id not in retained_nodes:
                if len(retained_nodes) >= limit:
                    break
                retained_nodes[node_id] = dict(node)

        retained_node_ids = set(retained_nodes)
        retained_edges: dict[str, dict[str, Any]] = {}
        for edge in edges:
            source_id = edge.start_node["id"]
            target_id = edge.end_node["id"]
            if source_id not in retained_node_ids or target_id not in retained_node_ids:
                continue
            retained_edges.setdefault(
                edge["id"],
                {
                    **dict(edge),
                    "source_id": source_id,
                    "target_id": target_id,
                },
            )
        return {
            "nodes": list(retained_nodes.values()),
            "edges": list(retained_edges.values()),
        }

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

    def qa_suggestion_candidate(self, project_id: str) -> dict[str, Any] | None:
        supported_properties = [
            "gender",
            "identity",
            "honorific",
            "life_status",
            "activity_region",
            "region",
            "characteristic",
        ]
        statement = """
            MATCH (person:Entity {project_id: $project_id, type: 'Person'})
            WHERE coalesce(person.review_status, 'ACCEPTED') <> 'MERGED'
            CALL (person) {
                OPTIONAL MATCH (fact:Fact {project_id: $project_id})-[:TARGET]->(person)
                WHERE fact.type = 'MASTER_OF'
                  AND coalesce(fact.review_status, 'ACCEPTED') <> 'REJECTED'
                OPTIONAL MATCH (fact)-[:SOURCE]->(source:Entity {project_id: $project_id})
                OPTIONAL MATCH (fact)-[:EVIDENCED_BY]->(evidence:Evidence {project_id: $project_id})
                WHERE source IS NOT NULL
                  AND coalesce(source.review_status, 'ACCEPTED') <> 'MERGED'
                RETURN collect(DISTINCT CASE WHEN evidence IS NOT NULL THEN fact END) AS master_facts
            }
            CALL (person) {
                OPTIONAL MATCH (fact:Fact {project_id: $project_id})-[:SOURCE]->(person)
                WHERE fact.type = 'MEMBER_OF'
                  AND coalesce(fact.review_status, 'ACCEPTED') <> 'REJECTED'
                OPTIONAL MATCH (fact)-[:TARGET]->(target:Entity {project_id: $project_id})
                OPTIONAL MATCH (fact)-[:EVIDENCED_BY]->(evidence:Evidence {project_id: $project_id})
                WHERE target IS NOT NULL
                  AND coalesce(target.review_status, 'ACCEPTED') <> 'MERGED'
                RETURN collect(DISTINCT CASE WHEN evidence IS NOT NULL THEN fact END) AS member_facts
            }
            CALL (person) {
                OPTIONAL MATCH (fact:Fact {project_id: $project_id})-[:SOURCE]->(person)
                WHERE fact.type = 'KNOWS'
                  AND coalesce(fact.review_status, 'ACCEPTED') <> 'REJECTED'
                OPTIONAL MATCH (fact)-[:TARGET]->(target:Entity {project_id: $project_id})
                OPTIONAL MATCH (fact)-[:EVIDENCED_BY]->(evidence:Evidence {project_id: $project_id})
                WHERE target IS NOT NULL
                  AND coalesce(target.review_status, 'ACCEPTED') <> 'MERGED'
                RETURN collect(DISTINCT CASE WHEN evidence IS NOT NULL THEN fact END) AS knows_facts
            }
            CALL (person) {
                OPTIONAL MATCH (person)-[:HAS_ATTRIBUTE]->(attribute:AttributeAssertion {project_id: $project_id})
                WHERE attribute.property_id IN $supported_properties
                  AND trim(toString(attribute.value)) <> ''
                OPTIONAL MATCH (attribute)-[:EVIDENCED_BY]->(evidence:Evidence {project_id: $project_id})
                WITH attribute, count(DISTINCT evidence) AS evidence_count
                WHERE attribute IS NOT NULL AND evidence_count > 0
                RETURN collect(DISTINCT attribute) AS attributes
            }
            WITH person, master_facts, member_facts, knows_facts, attributes,
                size(master_facts) + size(member_facts) + size(knows_facts) AS relationship_count,
                size(attributes) AS attribute_count
            WITH person, relationship_count, attribute_count,
                [capability IN [
                    CASE WHEN size(master_facts) > 0 THEN 'MASTER_OF' END,
                    CASE WHEN size(member_facts) > 0 THEN 'MEMBER_OF' END,
                    CASE WHEN size(knows_facts) > 0 THEN 'KNOWS' END
                ] WHERE capability IS NOT NULL] AS relation_capabilities,
                [property_id IN $supported_properties
                    WHERE any(attribute IN attributes
                        WHERE attribute.property_id = property_id)] AS property_capabilities
            WHERE relationship_count > 0 OR attribute_count > 0
            RETURN properties(person) AS entity,
                relation_capabilities,
                property_capabilities
            ORDER BY relationship_count DESC,
                attribute_count DESC,
                size(relation_capabilities) + size(property_capabilities) DESC,
                person.name,
                person.id
            LIMIT 1
        """
        with self.driver.session() as session:
            record = session.run(
                statement,
                project_id=project_id,
                supported_properties=supported_properties,
            ).single()
            if record is None:
                return None
            return {
                "entity": record["entity"],
                "relation_capabilities": record["relation_capabilities"],
                "property_capabilities": record["property_capabilities"],
            }

    def relation_detail(self, project_id: str, relation_id: str) -> dict[str, Any] | None:
        statement = """
            MATCH (fact:Fact {project_id: $project_id, id: $relation_id})
            WHERE coalesce(fact.review_status, 'ACCEPTED') <> 'REJECTED'
            MATCH (fact)-[:SOURCE]->(source:Entity {project_id: $project_id})
            MATCH (fact)-[:TARGET]->(target:Entity {project_id: $project_id})
            WHERE coalesce(source.review_status, 'ACCEPTED') <> 'MERGED'
              AND coalesce(target.review_status, 'ACCEPTED') <> 'MERGED'
            OPTIONAL MATCH (fact)-[:EVIDENCED_BY]->(evidence:Evidence)
                -[:IN_CHAPTER]->(chapter:Chapter)
            WITH fact, source, target, collect(DISTINCT {
                id: evidence.id,
                chapter_id: chapter.id,
                chapter_number: chapter.number,
                chapter_title: chapter.title,
                start_offset: evidence.start_offset,
                end_offset: evidence.end_offset,
                quote: evidence.quote
            }) AS evidence_rows
            RETURN {
                id: fact.id,
                type: fact.type,
                source_id: source.id,
                target_id: target.id,
                source: properties(source),
                target: properties(target),
                review_status: fact.review_status,
                evidence: [item IN evidence_rows WHERE item.id IS NOT NULL]
            } AS relation
        """
        with self.driver.session() as session:
            record = session.run(
                statement, project_id=project_id, relation_id=relation_id
            ).single()
            if record is None:
                return None
            relation = dict(record["relation"])
            relation["evidence"] = [
                item for item in relation.get("evidence", []) if item.get("id") is not None
            ]
            return relation

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

    def timeline_detail(
        self, project_id: str, event_id: str
    ) -> dict[str, Any] | None:
        statement = """
            MATCH (event:Entity {project_id: $project_id, id: $event_id})
            WHERE event.type IN ['Event', 'TeachingEvent']
              AND coalesce(event.review_status, 'ACCEPTED') <> 'MERGED'
            CALL {
                WITH event
                OPTIONAL MATCH (event)-[event_edge:RELATED]-(participant:Entity {project_id: $project_id})
                WHERE participant.type = 'Person'
                  AND coalesce(participant.review_status, 'ACCEPTED') <> 'MERGED'
                  AND coalesce(event_edge.review_status, 'ACCEPTED') <> 'REJECTED'
                RETURN min(event_edge.from_chapter) AS chapter_number,
                    [item IN collect(DISTINCT participant) WHERE item IS NOT NULL | properties(item)] AS participants
            }
            CALL {
                WITH event
                OPTIONAL MATCH (event_fact:Fact {project_id: $project_id})-[:SOURCE|TARGET]->(event)
                WHERE coalesce(event_fact.review_status, 'ACCEPTED') <> 'REJECTED'
                OPTIONAL MATCH (event_fact)-[:EVIDENCED_BY]->(event_evidence:Evidence)
                    -[:IN_CHAPTER]->(event_chapter:Chapter)
                WITH event_evidence, event_chapter
                ORDER BY event_chapter.number, event_evidence.start_offset
                WITH collect(DISTINCT {
                    id: event_evidence.id,
                    chapter_id: event_chapter.id,
                    chapter_number: event_chapter.number,
                    chapter_title: event_chapter.title,
                    start_offset: event_evidence.start_offset,
                    end_offset: event_evidence.end_offset,
                    quote: event_evidence.quote
                }) AS evidence_rows
                RETURN [item IN evidence_rows WHERE item.id IS NOT NULL] AS evidence
            }
            CALL {
                WITH event
                OPTIONAL MATCH (event)-[event_edge:RELATED]-(participant:Entity {project_id: $project_id})
                WHERE participant.type = 'Person'
                  AND coalesce(participant.review_status, 'ACCEPTED') <> 'MERGED'
                  AND coalesce(event_edge.review_status, 'ACCEPTED') <> 'REJECTED'
                WITH event, [item IN collect(DISTINCT participant.id) WHERE item IS NOT NULL] AS participant_ids
                UNWIND participant_ids AS participant_id
                MATCH (participant:Entity {project_id: $project_id, id: participant_id})
                MATCH (fact:Fact {project_id: $project_id})-[:SOURCE|TARGET]->(participant)
                MATCH (fact)-[:SOURCE]->(source:Entity {project_id: $project_id})
                MATCH (fact)-[:TARGET]->(target:Entity {project_id: $project_id})
                WHERE coalesce(fact.review_status, 'ACCEPTED') <> 'REJECTED'
                  AND coalesce(source.review_status, 'ACCEPTED') <> 'MERGED'
                  AND coalesce(target.review_status, 'ACCEPTED') <> 'MERGED'
                  AND source.id <> event.id AND target.id <> event.id
                WITH fact, source, target
                ORDER BY fact.id
                WITH collect(DISTINCT {
                    id: fact.id,
                    type: fact.type,
                    source: properties(source),
                    target: properties(target),
                    from_chapter: fact.from_chapter,
                    to_chapter: fact.to_chapter
                }) AS relationship_rows
                RETURN [item IN relationship_rows WHERE item.id IS NOT NULL] AS relationships
            }
            RETURN properties(event) AS event, chapter_number, participants, evidence, relationships
        """
        with self.driver.session() as session:
            record = session.run(
                statement, project_id=project_id, event_id=event_id
            ).single()
            if record is None:
                return None
            return {
                "event": dict(record["event"]),
                "chapter_number": record["chapter_number"],
                "participants": [dict(item) for item in record["participants"]],
                "evidence": [
                    dict(item) for item in record["evidence"] if item.get("id")
                ],
                "relationships": [
                    dict(item)
                    for item in record["relationships"]
                    if item.get("id")
                ],
            }

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
