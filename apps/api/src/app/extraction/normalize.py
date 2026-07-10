from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import hashlib
import re

from app.extraction.models import CandidateEvidence, ExtractionResult
from app.extraction.splitter import TextChunk
from app.graph.models import (
    AttributeAssertionRecord,
    EntityRecord,
    EvidenceRecord,
    FactRecord,
)
from app.ontology.models import (
    EntityType,
    PropertyDefinition,
    PropertyValueType,
    RelationType,
)
from app.ontology.properties import property_definition_for


MAX_EVIDENCE_QUOTE_LENGTH = 500
PURE_RELATIONSHIP_ROLE_VALUES = {
    "师父",
    "师傅",
    "徒弟",
    "弟子",
    "丈夫",
    "妻子",
    "配偶",
    "成员",
}


@dataclass(frozen=True)
class Rejection:
    code: str
    detail: str = ""


@dataclass
class NormalizedChunk:
    entities: list[EntityRecord] = field(default_factory=list)
    facts: list[FactRecord] = field(default_factory=list)
    attributes: list[AttributeAssertionRecord] = field(default_factory=list)
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


def _normalized_attribute_value(
    value: str, definition: PropertyDefinition
) -> tuple[str | None, str | None]:
    normalized = value.strip()
    if not normalized:
        return None, "EMPTY_ATTRIBUTE_VALUE"
    if definition.value_type == PropertyValueType.ENUM:
        if normalized not in definition.enum_values:
            return None, "INVALID_ATTRIBUTE_ENUM"
    elif definition.value_type == PropertyValueType.NUMBER:
        try:
            number = Decimal(normalized)
        except InvalidOperation:
            return None, "INVALID_ATTRIBUTE_NUMBER"
        if not number.is_finite():
            return None, "INVALID_ATTRIBUTE_NUMBER"
        normalized = format(number, "f")
        if "." in normalized:
            normalized = normalized.rstrip("0").rstrip(".")
        if normalized in {"", "-0"}:
            normalized = "0"
    elif definition.value_type == PropertyValueType.BOOLEAN:
        normalized = normalized.lower()
        if normalized not in {"true", "false"}:
            return None, "INVALID_ATTRIBUTE_BOOLEAN"
    return normalized, None


def normalize_chunk_result(
    project_id: str, chunk: TextChunk, result: ExtractionResult
) -> NormalizedChunk:
    normalized = NormalizedChunk()
    local_ids: dict[str, str] = {}
    entities_by_local_id: dict[str, EntityRecord] = {}
    evidence_by_id: dict[str, EvidenceRecord] = {}

    def evidence_record(
        evidence: CandidateEvidence, mismatch_code: str, too_long_code: str
    ) -> str | None:
        if len(evidence.quote) > MAX_EVIDENCE_QUOTE_LENGTH:
            normalized.rejections.append(Rejection(too_long_code))
            return None
        aligned_range = _aligned_evidence_range(
            chunk.text, evidence.start, evidence.end, evidence.quote
        )
        if aligned_range is None:
            normalized.rejections.append(Rejection(mismatch_code))
            return None
        aligned_start, aligned_end = aligned_range
        absolute_start = chunk.start_offset + aligned_start
        absolute_end = chunk.start_offset + aligned_end
        evidence_id = (
            f"{project_id}:evidence:"
            f"{_stable_id(str(absolute_start), str(absolute_end), evidence.quote)}"
        )
        if evidence_id not in evidence_by_id:
            record = EvidenceRecord(
                id=evidence_id,
                chapter_id=f"{project_id}:chapter:{chunk.chapter_number}",
                start_offset=absolute_start,
                end_offset=absolute_end,
                quote=evidence.quote,
                text_hash=hashlib.sha256(evidence.quote.encode()).hexdigest(),
            )
            evidence_by_id[evidence_id] = record
            normalized.evidence.append(record)
        return evidence_id

    for candidate in result.entities:
        local_id = candidate.local_id.strip()
        name = candidate.name.strip()
        entity_type_text = candidate.type.strip()
        if not local_id:
            normalized.rejections.append(Rejection("EMPTY_ENTITY_LOCAL_ID"))
            continue
        if not name:
            normalized.rejections.append(Rejection("EMPTY_ENTITY_NAME"))
            continue
        if not entity_type_text:
            normalized.rejections.append(Rejection("EMPTY_ENTITY_TYPE"))
            continue
        try:
            entity_type = EntityType(entity_type_text)
        except ValueError:
            normalized.rejections.append(
                Rejection("UNKNOWN_ENTITY_TYPE", entity_type_text)
            )
            continue
        entity_id = f"{project_id}:{entity_type.value}:{_stable_id(name)}"
        local_ids[local_id] = entity_id
        entity_record = EntityRecord(
            id=entity_id,
            type=entity_type,
            name=name,
            aliases=sorted(
                set(alias.strip() for alias in candidate.aliases if alias.strip())
            ),
        )
        entities_by_local_id[local_id] = entity_record
        normalized.entities.append(entity_record)

    for candidate in result.facts:
        relation_text = candidate.relation.strip()
        try:
            relation = RelationType(relation_text)
        except ValueError:
            normalized.rejections.append(
                Rejection("UNKNOWN_RELATION_TYPE", relation_text)
            )
            continue
        source_id = local_ids.get(candidate.source_local_id.strip())
        target_id = local_ids.get(candidate.target_local_id.strip())
        if not source_id or not target_id:
            normalized.rejections.append(Rejection("UNKNOWN_FACT_ENTITY"))
            continue
        evidence_id = evidence_record(
            candidate.evidence, "EVIDENCE_MISMATCH", "EVIDENCE_TOO_LONG"
        )
        if evidence_id is None:
            continue
        fact_id = f"{project_id}:fact:{_stable_id(relation.value, source_id, target_id)}"
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

    for candidate in result.attributes:
        entity = entities_by_local_id.get(candidate.entity_local_id.strip())
        if entity is None:
            normalized.rejections.append(Rejection("UNKNOWN_ATTRIBUTE_ENTITY"))
            continue
        property_id = candidate.property_id.strip()
        definition = property_definition_for(entity.type, property_id)
        if definition is None:
            normalized.rejections.append(
                Rejection("UNKNOWN_ENTITY_PROPERTY", property_id)
            )
            continue
        value, rejection_code = _normalized_attribute_value(
            candidate.value, definition
        )
        if rejection_code is not None:
            normalized.rejections.append(Rejection(rejection_code))
            continue
        assert value is not None
        other_entity_names = {
            name
            for local_id, candidate_entity in entities_by_local_id.items()
            if local_id != candidate.entity_local_id.strip()
            for name in (candidate_entity.name, *candidate_entity.aliases)
        }
        if value in PURE_RELATIONSHIP_ROLE_VALUES or value in other_entity_names:
            normalized.rejections.append(Rejection("RELATION_SEMANTIC_ATTRIBUTE"))
            continue
        evidence_id = evidence_record(
            candidate.evidence,
            "ATTRIBUTE_EVIDENCE_MISMATCH",
            "ATTRIBUTE_EVIDENCE_TOO_LONG",
        )
        if evidence_id is None:
            continue
        attribute_id = (
            f"{project_id}:attribute:"
            f"{_stable_id(project_id, entity.id, property_id, value)}"
        )
        normalized.attributes.append(
            AttributeAssertionRecord(
                id=attribute_id,
                entity_id=entity.id,
                entity_name=entity.name,
                entity_type=entity.type,
                property_id=property_id,
                value=value,
                value_type=definition.value_type,
                confidence=candidate.confidence,
                evidence_ids=[evidence_id],
            )
        )
    return normalized
