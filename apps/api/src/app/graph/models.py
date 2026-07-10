from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from app.ontology.models import EntityType, PropertyValueType, RelationType


class ProjectRecord(BaseModel):
    id: str
    title: str


class ChapterRecord(BaseModel):
    id: str
    number: int = Field(ge=1)
    title: str


class EntityRecord(BaseModel):
    id: str
    type: EntityType
    name: str
    aliases: list[str] = Field(default_factory=list)
    description: str = ""


class FactRecord(BaseModel):
    id: str
    type: RelationType
    source_id: str
    target_id: str
    evidence_ids: list[str] = Field(min_length=1)
    from_chapter: int | None = Field(default=None, ge=1)
    to_chapter: int | None = Field(default=None, ge=1)
    confidence: float = Field(default=1.0, ge=0, le=1)


class AttributeAssertionRecord(BaseModel):
    id: str
    entity_id: str
    entity_name: str
    entity_type: EntityType
    property_id: str
    value: str
    value_type: PropertyValueType
    confidence: float = Field(default=1.0, ge=0, le=1)
    evidence_ids: list[str] = Field(min_length=1)


class EvidenceRecord(BaseModel):
    id: str
    chapter_id: str
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=500)
    text_hash: str = Field(min_length=1)

    @model_validator(mode="after")
    def offset_order(self) -> Self:
        if self.end_offset <= self.start_offset:
            raise ValueError("end_offset must be greater than start_offset")
        return self


class GraphDocument(BaseModel):
    project: ProjectRecord
    chapters: list[ChapterRecord]
    entities: list[EntityRecord]
    facts: list[FactRecord]
    evidence: list[EvidenceRecord]
    attributes: list[AttributeAssertionRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def references_exist(self) -> Self:
        entity_ids = {item.id for item in self.entities}
        chapter_ids = {item.id for item in self.chapters}
        evidence_ids = {item.id for item in self.evidence}
        for fact in self.facts:
            if fact.source_id not in entity_ids or fact.target_id not in entity_ids:
                raise ValueError(f"fact {fact.id} references an unknown entity")
            if not set(fact.evidence_ids) <= evidence_ids:
                raise ValueError(f"fact {fact.id} references unknown evidence")
        for attribute in self.attributes:
            if attribute.entity_id not in entity_ids:
                raise ValueError(
                    f"attribute {attribute.id} references an unknown entity"
                )
            if not set(attribute.evidence_ids) <= evidence_ids:
                raise ValueError(f"attribute {attribute.id} references unknown evidence")
        for item in self.evidence:
            if item.chapter_id not in chapter_ids:
                raise ValueError(f"evidence {item.id} references an unknown chapter")
        return self


class ImportSummary(BaseModel):
    created_entities: int = 0
    created_facts: int = 0
    created_evidence: int = 0
    created_attributes: int = 0


class EntitySummary(BaseModel):
    id: str
    project_id: str
    type: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    review_status: str | None = None
    merged_into: str | None = None


class GraphEdge(BaseModel):
    id: str
    source_id: str
    target_id: str
    type: str
    from_chapter: int | None = None
    to_chapter: int | None = None
    confidence: float = 1.0
    review_status: str | None = None


class Neighborhood(BaseModel):
    nodes: list[EntitySummary]
    edges: list[GraphEdge]


class EvidenceDetail(BaseModel):
    id: str
    chapter_id: str
    chapter_number: int
    chapter_title: str
    start_offset: int
    end_offset: int
    quote: str


class RelatedFact(BaseModel):
    id: str
    type: str
    source_id: str
    target_id: str
    review_status: str | None = None
    evidence: list[EvidenceDetail] = Field(default_factory=list)


class AttributeDetail(BaseModel):
    id: str
    property_id: str
    label: str
    value_type: str
    value: str
    confidence: float = 1.0
    evidence: list[EvidenceDetail] = Field(default_factory=list)


class RelationEntity(BaseModel):
    id: str
    type: str
    name: str


class RelationSummary(BaseModel):
    fact_id: str
    type: str
    label: str
    direction: Literal["OUTGOING", "INCOMING"]
    other: RelationEntity


class EntityDetail(EntitySummary):
    attributes: list[AttributeDetail] = Field(default_factory=list)
    relations: list[RelationSummary] = Field(default_factory=list)
    facts: list[RelatedFact] = Field(default_factory=list)


class TimelineEvent(BaseModel):
    event: EntitySummary
    chapter_number: int | None = None
