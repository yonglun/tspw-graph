import hashlib
from typing import Any, Protocol

from app.graph.models import GraphDocument, ImportSummary


class GraphWriter(Protocol):
    def ensure_constraints(self) -> None: ...

    def upsert_batch(self, label: str, rows: list[dict[str, Any]]) -> int: ...

    def upsert_attribute_bundle(
        self,
        project_id: str,
        hints: list[dict[str, str]],
        attributes: list[dict[str, Any]],
        evidence: list[dict[str, Any]],
        protected_evidence_ids: set[str],
    ) -> ImportSummary: ...


class GraphImporter:
    def __init__(self, writer: GraphWriter) -> None:
        self.writer = writer

    def import_document(self, document: GraphDocument) -> ImportSummary:
        self.writer.ensure_constraints()
        project_id = document.project.id
        self.writer.upsert_batch(
            "Project", [{"id": project_id, **document.project.model_dump()}]
        )
        self.writer.upsert_batch(
            "Chapter",
            [
                {"project_id": project_id, **chapter.model_dump()}
                for chapter in document.chapters
            ],
        )
        created_entities = self.writer.upsert_batch(
            "Entity",
            [
                {"project_id": project_id, **entity.model_dump(mode="json")}
                for entity in document.entities
            ],
        )
        fact_evidence_ids = {
            evidence_id
            for fact in document.facts
            for evidence_id in fact.evidence_ids
        }
        attribute_summary = self.writer.upsert_attribute_bundle(
            project_id,
            self._attribute_hints(document),
            [item.model_dump(mode="json") for item in document.attributes],
            [item.model_dump() for item in document.evidence],
            fact_evidence_ids,
        )
        created_facts = self.writer.upsert_batch(
            "Fact",
            [
                {"project_id": project_id, **fact.model_dump(mode="json")}
                for fact in document.facts
            ],
        )
        return ImportSummary(
            created_entities=created_entities,
            created_facts=created_facts,
            created_evidence=attribute_summary.created_evidence,
            created_attributes=attribute_summary.created_attributes,
            retained_attributes=attribute_summary.retained_attributes,
            retained_attribute_evidence=attribute_summary.retained_attribute_evidence,
            retained_evidence=attribute_summary.retained_evidence,
        )

    def import_attributes(self, document: GraphDocument) -> ImportSummary:
        self.writer.ensure_constraints()
        project_id = document.project.id
        return self.writer.upsert_attribute_bundle(
            project_id,
            self._attribute_hints(document),
            [item.model_dump(mode="json") for item in document.attributes],
            [item.model_dump() for item in document.evidence],
            set(),
        )

    @staticmethod
    def _attribute_hints(document: GraphDocument) -> list[dict[str, str]]:
        attribute_entity_ids = {
            attribute.entity_id for attribute in document.attributes
        }
        return [
            {"id": entity.id, "name": entity.name, "type": entity.type.value}
            for entity in document.entities
            if entity.id in attribute_entity_ids
        ]


def canonicalize_attribute_rows(
    project_id: str,
    attributes: list[dict[str, Any]],
    mappings: dict[str, str],
) -> list[dict[str, Any]]:
    resolved: dict[str, dict[str, Any]] = {}
    for attribute in attributes:
        canonical_id = mappings.get(attribute["entity_id"])
        if canonical_id is None:
            continue
        digest = hashlib.sha256(
            "|".join(
                (
                    project_id,
                    canonical_id,
                    attribute["property_id"],
                    attribute["value"],
                )
            ).encode()
        ).hexdigest()[:16]
        assertion_id = f"{project_id}:attribute:{digest}"
        row = {
            "project_id": project_id,
            **attribute,
            "id": assertion_id,
            "entity_id": canonical_id,
        }
        existing = resolved.get(assertion_id)
        if existing is None:
            resolved[assertion_id] = row
        else:
            existing["evidence_ids"] = sorted(
                set(existing["evidence_ids"] + row["evidence_ids"])
            )
    return list(resolved.values())
