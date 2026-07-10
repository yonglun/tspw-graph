import hashlib
from typing import Any, Protocol

from app.graph.models import GraphDocument, ImportSummary


class GraphWriter(Protocol):
    def ensure_constraints(self) -> None: ...

    def upsert_batch(self, label: str, rows: list[dict[str, Any]]) -> int: ...

    def resolve_attribute_entities(
        self, project_id: str, hints: list[dict[str, str]]
    ) -> dict[str, str]: ...


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
        attributes = self._resolved_attributes(document)
        referenced_evidence_ids = {
            evidence_id
            for fact in document.facts
            for evidence_id in fact.evidence_ids
        } | {
            evidence_id
            for attribute in attributes
            for evidence_id in attribute["evidence_ids"]
        }
        created_evidence = self.writer.upsert_batch(
            "Evidence",
            [
                {"project_id": project_id, **item.model_dump()}
                for item in document.evidence
                if item.id in referenced_evidence_ids
            ],
        )
        created_attributes = self.writer.upsert_batch(
            "AttributeAssertion",
            attributes,
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
            created_evidence=created_evidence,
            created_attributes=created_attributes,
            retained_attributes=len(attributes),
            retained_attribute_evidence=len(
                {
                    evidence_id
                    for attribute in attributes
                    for evidence_id in attribute["evidence_ids"]
                }
            ),
            retained_evidence=len(referenced_evidence_ids),
        )

    def import_attributes(self, document: GraphDocument) -> ImportSummary:
        self.writer.ensure_constraints()
        project_id = document.project.id
        attributes = self._resolved_attributes(document)
        referenced_evidence_ids = {
            evidence_id
            for attribute in attributes
            for evidence_id in attribute["evidence_ids"]
        }
        created_evidence = self.writer.upsert_batch(
            "Evidence",
            [
                {"project_id": project_id, **item.model_dump()}
                for item in document.evidence
                if item.id in referenced_evidence_ids
            ],
        )
        created_attributes = self.writer.upsert_batch(
            "AttributeAssertion",
            attributes,
        )
        return ImportSummary(
            created_evidence=created_evidence,
            created_attributes=created_attributes,
            retained_attributes=len(attributes),
            retained_attribute_evidence=len(referenced_evidence_ids),
            retained_evidence=len(referenced_evidence_ids),
        )

    def _resolved_attributes(self, document: GraphDocument) -> list[dict[str, Any]]:
        project_id = document.project.id
        attribute_entity_ids = {
            attribute.entity_id for attribute in document.attributes
        }
        mappings = self.writer.resolve_attribute_entities(
            project_id,
            [
                {
                    "id": entity.id,
                    "name": entity.name,
                    "type": entity.type.value,
                }
                for entity in document.entities
                if entity.id in attribute_entity_ids
            ],
        )
        resolved: dict[str, dict[str, Any]] = {}
        for attribute in document.attributes:
            canonical_id = mappings.get(attribute.entity_id)
            if canonical_id is None:
                continue
            digest = hashlib.sha256(
                "|".join(
                    (
                        project_id,
                        canonical_id,
                        attribute.property_id,
                        attribute.value,
                    )
                ).encode()
            ).hexdigest()[:16]
            assertion_id = f"{project_id}:attribute:{digest}"
            row = {
                "project_id": project_id,
                **attribute.model_dump(mode="json"),
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
