from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExtractionRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=100)
    chunk_id: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=20_000)
    ontology: dict[str, Any]


class CandidateEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    local_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    name: str = Field(min_length=1, max_length=100)
    type: str = Field(min_length=1, max_length=50)
    aliases: list[str] = Field(default_factory=list, max_length=20)


class CandidateEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=500)


class CandidateFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relation: str = Field(min_length=1, max_length=50)
    source_local_id: str = Field(min_length=1, max_length=64)
    target_local_id: str = Field(min_length=1, max_length=64)
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
