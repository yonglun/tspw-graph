from dataclasses import dataclass, field
import hashlib
import re

from app.extraction.models import ExtractionResult
from app.extraction.splitter import TextChunk
from app.graph.models import EntityRecord, EvidenceRecord, FactRecord
from app.ontology.models import EntityType, RelationType


@dataclass(frozen=True)
class Rejection:
    code: str
    detail: str = ""


@dataclass
class NormalizedChunk:
    entities: list[EntityRecord] = field(default_factory=list)
    facts: list[FactRecord] = field(default_factory=list)
    evidence: list[EvidenceRecord] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)


def _stable_id(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
    return digest


def _aligned_evidence_range(chunk_text: str, start: int, end: int, quote: str) -> tuple[int, int] | None:
    if not quote:
        return None
    if start < end and end <= len(chunk_text) and chunk_text[start:end] == quote:
        return start, end

    matches = [match.start() for match in re.finditer(re.escape(quote), chunk_text)]
    if not matches:
        return None
    aligned_start = min(matches, key=lambda index: abs(index - start))
    return aligned_start, aligned_start + len(quote)


def normalize_chunk_result(
    project_id: str, chunk: TextChunk, result: ExtractionResult
) -> NormalizedChunk:
    normalized = NormalizedChunk()
    local_ids: dict[str, str] = {}
    for candidate in result.entities:
        try:
            entity_type = EntityType(candidate.type)
        except ValueError:
            normalized.rejections.append(
                Rejection("UNKNOWN_ENTITY_TYPE", candidate.type)
            )
            continue
        entity_id = f"{project_id}:{entity_type.value}:{_stable_id(candidate.name)}"
        local_ids[candidate.local_id] = entity_id
        normalized.entities.append(
            EntityRecord(
                id=entity_id,
                type=entity_type,
                name=candidate.name.strip(),
                aliases=sorted(set(candidate.aliases)),
            )
        )

    for candidate in result.facts:
        try:
            relation = RelationType(candidate.relation)
        except ValueError:
            normalized.rejections.append(
                Rejection("UNKNOWN_RELATION_TYPE", candidate.relation)
            )
            continue
        source_id = local_ids.get(candidate.source_local_id)
        target_id = local_ids.get(candidate.target_local_id)
        if not source_id or not target_id:
            normalized.rejections.append(Rejection("UNKNOWN_FACT_ENTITY"))
            continue
        evidence = candidate.evidence
        aligned_range = _aligned_evidence_range(
            chunk.text, evidence.start, evidence.end, evidence.quote
        )
        if aligned_range is None:
            normalized.rejections.append(Rejection("EVIDENCE_MISMATCH"))
            continue
        aligned_start, aligned_end = aligned_range
        absolute_start = chunk.start_offset + aligned_start
        absolute_end = chunk.start_offset + aligned_end
        evidence_id = f"{project_id}:evidence:{_stable_id(chunk.id, str(absolute_start), evidence.quote)}"
        fact_id = f"{project_id}:fact:{_stable_id(relation.value, source_id, target_id)}"
        normalized.evidence.append(
            EvidenceRecord(
                id=evidence_id,
                chapter_id=f"{project_id}:chapter:{chunk.chapter_number}",
                start_offset=absolute_start,
                end_offset=absolute_end,
                quote=evidence.quote,
                text_hash=hashlib.sha256(evidence.quote.encode()).hexdigest(),
            )
        )
        normalized.facts.append(
            FactRecord(
                id=fact_id,
                type=relation,
                source_id=source_id,
                target_id=target_id,
                evidence_ids=[evidence_id],
                from_chapter=chunk.chapter_number,
                confidence=candidate.confidence,
            )
        )
    return normalized
