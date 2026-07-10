from typing import Any, Protocol

from app.graph.models import GraphDocument, ImportSummary


class GraphWriter(Protocol):
    def ensure_constraints(self) -> None: ...

    def upsert_batch(self, label: str, rows: list[dict[str, Any]]) -> int: ...


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
        created_evidence = self.writer.upsert_batch(
            "Evidence",
            [
                {"project_id": project_id, **item.model_dump()}
                for item in document.evidence
            ],
        )
        created_attributes = self.writer.upsert_batch(
            "AttributeAssertion",
            [
                {"project_id": project_id, **item.model_dump(mode="json")}
                for item in document.attributes
            ],
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
        )
