from typing import Any

from app.graph.models import (
    EntityDetail,
    EntitySummary,
    EvidenceDetail,
    GraphEdge,
    Neighborhood,
    RelatedFact,
    TimelineEvent,
)


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
        grouped: dict[str, dict[str, Any]] = {}
        for row in result["rows"]:
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
                fact["evidence"].append(EvidenceDetail.model_validate(evidence))
        entity = EntitySummary.model_validate(result["entity"])
        return EntityDetail(
            **entity.model_dump(),
            facts=[RelatedFact.model_validate(item) for item in grouped.values()],
        )

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
