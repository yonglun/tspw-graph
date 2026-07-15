from typing import Literal

from pydantic import BaseModel, Field

from app.graph.models import EvidenceDetail


class AskRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=2, max_length=200)


class QaPathStep(BaseModel):
    source_name: str
    relation: str
    target_name: str


class AskResponse(BaseModel):
    answer: str
    path: list[QaPathStep] = Field(default_factory=list)
    query_explanation: str
    cypher_template: str
    parameters: dict[str, str]
    evidence: list[EvidenceDetail] = Field(default_factory=list)


class QaRepresentativeEntity(BaseModel):
    id: str
    name: str
    type: str


class QaSuggestion(BaseModel):
    id: str
    question: str
    kind: Literal["relation", "attribute"]
    capability: str


class QaSuggestionsResponse(BaseModel):
    project_id: str
    project_title: str
    representative_entity: QaRepresentativeEntity | None = None
    suggestions: list[QaSuggestion] = Field(default_factory=list)
