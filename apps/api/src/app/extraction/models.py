from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExtractionRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=100)
    chunk_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=20_000)
    ontology: dict[str, Any]


class CandidateEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    local_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=50)
    aliases: list[str] = Field(default_factory=list, max_length=20)


class CandidateEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    quote: str


class CandidateFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relation: str = Field(min_length=1, max_length=50)
    source_local_id: str = Field(max_length=100)
    target_local_id: str = Field(max_length=100)
    evidence: CandidateEvidence
    confidence: float = Field(default=1.0, ge=0, le=1)


class ExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entities: list[CandidateEntity] = Field(default_factory=list, max_length=100)
    facts: list[CandidateFact] = Field(default_factory=list, max_length=200)

    def validate_for_chunk(self, chunk: str) -> None:
        for fact in self.facts:
            evidence = fact.evidence
            if evidence.end > len(chunk) or evidence.start >= evidence.end:
                raise ValueError("EVIDENCE_OFFSET_OUT_OF_RANGE")
            if chunk[evidence.start : evidence.end] != evidence.quote:
                raise ValueError("EVIDENCE_QUOTE_MISMATCH")


def strict_extraction_schema() -> dict[str, Any]:
    """JSON Schema subset accepted by strict structured outputs.

    Pydantic's generated schema is valid JSON Schema, but strict structured
    output endpoints require every object property to be listed in `required`
    and reject defaults. Keep this schema intentionally small and let the
    Pydantic models above enforce fine-grained validation after the model
    returns JSON.
    """
    evidence = {
        "type": "object",
        "properties": {
            "start": {"type": "integer"},
            "end": {"type": "integer"},
            "quote": {"type": "string"},
        },
        "required": ["start", "end", "quote"],
        "additionalProperties": False,
    }
    entity = {
        "type": "object",
        "properties": {
            "local_id": {"type": "string"},
            "name": {"type": "string"},
            "type": {"type": "string"},
            "aliases": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["local_id", "name", "type", "aliases"],
        "additionalProperties": False,
    }
    fact = {
        "type": "object",
        "properties": {
            "relation": {"type": "string"},
            "source_local_id": {"type": "string"},
            "target_local_id": {"type": "string"},
            "evidence": evidence,
            "confidence": {"type": "number"},
        },
        "required": [
            "relation",
            "source_local_id",
            "target_local_id",
            "evidence",
            "confidence",
        ],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "entities": {"type": "array", "items": entity},
            "facts": {"type": "array", "items": fact},
        },
        "required": ["entities", "facts"],
        "additionalProperties": False,
    }
