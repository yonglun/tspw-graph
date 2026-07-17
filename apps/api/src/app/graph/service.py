from typing import Any

from app.graph.models import (
    AttributeDetail,
    EntityDetail,
    EntitySummary,
    EvidenceDetail,
    GraphEdge,
    Neighborhood,
    RelationSummary,
    RelatedFact,
    TimelineEvent,
    TimelineEventDetail,
    TimelineRelationship,
    TimelineRelationshipStates,
)
from app.ontology.catalog import relation_by_id
from app.ontology.models import EntityType
from app.ontology.properties import property_definition_for


class EntityNotFoundError(LookupError):
    pass


class GraphService:
    def __init__(self, repository: Any) -> None:
        self.repository = repository

    def search(
        self, project_id: str, query: str, types: list[str], limit: int
    ) -> list[EntitySummary]:
        exact_rows = self._project_rows(
            self.repository.search_exact(project_id, query, types, limit), project_id
        )
        rows = self._deduplicate(exact_rows)[:limit]
        if len(rows) < limit:
            contains_rows = self._project_rows(
                self.repository.search_contains(
                    project_id, query, types, limit - len(rows)
                ),
                project_id,
            )
            rows = self._deduplicate([*rows, *contains_rows])[:limit]
        return [EntitySummary.model_validate(row) for row in rows]

    def neighborhood(
        self,
        project_id: str,
        entity_id: str,
        depth: int,
        limit: int,
        from_chapter: int | None,
        to_chapter: int | None,
    ) -> Neighborhood:
        result = self.repository.neighborhood(
            project_id,
            entity_id,
            depth,
            limit,
            from_chapter,
            to_chapter,
        )
        if result is None:
            raise EntityNotFoundError(entity_id)
        return Neighborhood(
            nodes=[EntitySummary.model_validate(row) for row in result["nodes"]],
            edges=[
                GraphEdge.model_validate(row)
                for row in result["edges"]
                if row.get("review_status") != "REJECTED"
            ],
        )

    @staticmethod
    def _project_rows(
        rows: list[dict[str, Any]], project_id: str
    ) -> list[dict[str, Any]]:
        return [row for row in rows if row.get("project_id") == project_id]

    @staticmethod
    def _deduplicate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        unique: dict[str, dict[str, Any]] = {}
        for row in rows:
            entity_id = row.get("id")
            if isinstance(entity_id, str) and entity_id not in unique:
                unique[entity_id] = row
        return list(unique.values())

    def shortest_path(
        self, project_id: str, source_id: str, target_id: str, max_depth: int
    ) -> Neighborhood:
        result = self.repository.shortest_path(
            project_id, source_id, target_id, max_depth
        )
        return Neighborhood(
            nodes=[EntitySummary.model_validate(row) for row in result["nodes"]],
            edges=[GraphEdge.model_validate(row) for row in result["edges"]],
        )

    def entity_detail(self, project_id: str, entity_id: str) -> EntityDetail:
        result = self.repository.entity_detail(project_id, entity_id)
        if result is None:
            raise EntityNotFoundError(entity_id)
        entity = EntitySummary.model_validate(result["entity"])
        attributes = self._attribute_details(entity, result.get("attributes", []))
        facts = self._related_facts(result.get("rows", []))
        relations = self._relation_summaries(entity_id, result.get("rows", []))
        return EntityDetail(
            **entity.model_dump(),
            attributes=attributes,
            relations=relations,
            facts=facts,
        )

    def relation_detail(self, project_id: str, relation_id: str) -> RelatedFact:
        result = self.repository.relation_detail(project_id, relation_id)
        if result is None:
            raise EntityNotFoundError(relation_id)
        relation = relation_by_id(result.get("type", ""))
        return RelatedFact.model_validate(
            {
                **result,
                "label": relation.label if relation else result.get("type", ""),
                "evidence": self._deduplicate_evidence(result.get("evidence", [])),
            }
        )

    def _attribute_details(
        self, entity: EntitySummary, rows: list[dict[str, Any]]
    ) -> list[AttributeDetail]:
        try:
            entity_type = EntityType(entity.type)
        except ValueError:
            entity_type = None
        details: list[AttributeDetail] = []
        for row in rows:
            if row.get("id") is None:
                continue
            property_id = row.get("property_id", "")
            definition = (
                property_definition_for(entity_type, property_id)
                if entity_type is not None
                else None
            )
            details.append(
                AttributeDetail.model_validate(
                    {
                        **row,
                        "label": definition.label if definition else property_id,
                        "evidence": self._deduplicate_evidence(row.get("evidence", [])),
                    }
                )
            )
        return details

    def _related_facts(self, rows: list[dict[str, Any]]) -> list[RelatedFact]:
        grouped: dict[str, dict[str, Any]] = {}
        for row in rows:
            if row.get("id") is None:
                continue
            fact = grouped.setdefault(
                row["id"],
                {
                    "id": row["id"],
                    "type": row["type"],
                    "source_id": row["source_id"],
                    "target_id": row["target_id"],
                    "review_status": row.get("review_status"),
                    "evidence": [],
                },
            )
            evidence = row.get("evidence")
            if evidence and evidence.get("id") is not None:
                fact["evidence"].append(evidence)
        return [
            RelatedFact.model_validate(
                {**item, "evidence": self._deduplicate_evidence(item["evidence"])}
            )
            for item in grouped.values()
        ]

    def _relation_summaries(
        self, entity_id: str, rows: list[dict[str, Any]]
    ) -> list[RelationSummary]:
        summaries: dict[str, RelationSummary] = {}
        for row in rows:
            fact_id = row.get("id")
            if fact_id is None or fact_id in summaries:
                continue
            source = row.get("source") or {}
            target = row.get("target") or {}
            if row.get("source_id") == entity_id:
                direction = "OUTGOING"
                other = target
            elif row.get("target_id") == entity_id:
                direction = "INCOMING"
                other = source
            else:
                continue
            if not other.get("id"):
                continue
            relation = relation_by_id(row.get("type", ""))
            summaries[fact_id] = RelationSummary.model_validate(
                {
                    "fact_id": fact_id,
                    "type": row.get("type", ""),
                    "label": relation.label if relation else row.get("type", ""),
                    "direction": direction,
                    "other": other,
                }
            )
        return list(summaries.values())

    @staticmethod
    def _deduplicate_evidence(rows: list[dict[str, Any]]) -> list[EvidenceDetail]:
        unique: dict[str, EvidenceDetail] = {}
        for row in rows:
            if row.get("id") is not None and row["id"] not in unique:
                unique[row["id"]] = EvidenceDetail.model_validate(row)
        return list(unique.values())

    def timeline(
        self,
        project_id: str,
        person_id: str | None,
        from_chapter: int | None,
        to_chapter: int | None,
        limit: int,
    ) -> list[TimelineEvent]:
        return [
            TimelineEvent.model_validate(row)
            for row in self.repository.timeline(
                project_id, person_id, from_chapter, to_chapter, limit
            )
        ]

    def timeline_participants(
        self, project_id: str, limit: int
    ) -> list[EntitySummary]:
        rows = self._project_rows(
            self.repository.timeline_participants(project_id, limit), project_id
        )
        people = [row for row in rows if row.get("type") == "Person"]
        return [
            EntitySummary.model_validate(row)
            for row in self._deduplicate(people)[:limit]
        ]

    def timeline_detail(
        self, project_id: str, event_id: str
    ) -> TimelineEventDetail:
        result = self.repository.timeline_detail(project_id, event_id)
        if result is None:
            raise EntityNotFoundError(event_id)

        event = EntitySummary.model_validate(result["event"])
        participants = [
            EntitySummary.model_validate(row)
            for row in self._deduplicate(result.get("participants", []))
        ]
        chapter_number = result.get("chapter_number")
        states = self._timeline_states(
            result.get("relationships", []), chapter_number
        )
        return TimelineEventDetail(
            event=event,
            chapter_number=chapter_number,
            participants=participants,
            evidence=self._deduplicate_evidence(result.get("evidence", [])),
            relationship_states=states,
        )

    @staticmethod
    def _timeline_relationship(row: dict[str, Any]) -> TimelineRelationship:
        relation = relation_by_id(row.get("type", ""))
        return TimelineRelationship.model_validate(
            {
                **row,
                "label": relation.label if relation else row.get("type", ""),
            }
        )

    def _timeline_states(
        self, rows: list[dict[str, Any]], chapter_number: int | None
    ) -> TimelineRelationshipStates:
        if chapter_number is None:
            return TimelineRelationshipStates()

        started: list[TimelineRelationship] = []
        active: list[TimelineRelationship] = []
        ended: list[TimelineRelationship] = []
        seen: set[str] = set()
        for row in rows:
            fact_id = row.get("id")
            if not isinstance(fact_id, str) or fact_id in seen:
                continue
            seen.add(fact_id)
            from_chapter = row.get("from_chapter")
            to_chapter = row.get("to_chapter")
            relationship = self._timeline_relationship(row)
            if from_chapter == chapter_number:
                started.append(relationship)
            elif to_chapter == chapter_number:
                ended.append(relationship)
            elif (
                from_chapter is None or from_chapter < chapter_number
            ) and (to_chapter is None or to_chapter > chapter_number):
                active.append(relationship)

        return TimelineRelationshipStates(
            started=started,
            active=active,
            ended=ended,
        )
