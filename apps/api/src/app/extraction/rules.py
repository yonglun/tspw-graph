from collections.abc import Iterable
import re

from app.extraction.models import (
    CandidateEntity,
    CandidateEvidence,
    CandidateFact,
    ExtractionResult,
)
from app.extraction.splitter import TextChunk


NAME = r"[\u4e00-\u9fff]{1,12}"

RULES: tuple[tuple[str, str, str, str], ...] = (
    (
        "MASTER_OF",
        "master",
        "student",
        rf"(?P<student>{NAME})的(?:师父|師父|师傅|師傅|师尊)是(?P<master>{NAME})",
    ),
    (
        "MASTER_OF",
        "master",
        "student",
        rf"(?P<master>{NAME})是(?P<student>{NAME})的(?:师父|師父|师傅|師傅|师尊)",
    ),
    (
        "SPOUSE_OF",
        "wife",
        "husband",
        rf"(?P<wife>{NAME})是(?P<husband>{NAME})的(?:妻子|夫人)",
    ),
    (
        "SPOUSE_OF",
        "wife",
        "husband",
        rf"(?P<husband>{NAME})的(?:妻子|夫人)(?:是)?(?P<wife>{NAME})",
    ),
)


def _local_id(name: str) -> str:
    return f"rule_person_{name}"


def _entity(name: str) -> CandidateEntity:
    return CandidateEntity(
        local_id=_local_id(name),
        name=name,
        type="Person",
        aliases=[],
    )


def _existing_entity_names(result: ExtractionResult) -> set[str]:
    return {entity.name for entity in result.entities}


def _existing_fact_keys(result: ExtractionResult) -> set[tuple[str, str, str, str]]:
    return {
        (
            fact.relation,
            fact.source_local_id,
            fact.target_local_id,
            fact.evidence.quote,
        )
        for fact in result.facts
    }


def _rule_facts(chunk: TextChunk) -> Iterable[tuple[CandidateFact, list[str]]]:
    for relation, source_group, target_group, pattern in RULES:
        for match in re.finditer(pattern, chunk.text):
            source_name = match.group(source_group)
            target_name = match.group(target_group)
            quote = match.group(0)
            yield (
                CandidateFact(
                    relation=relation,
                    source_local_id=_local_id(source_name),
                    target_local_id=_local_id(target_name),
                    evidence=CandidateEvidence(
                        start=match.start(),
                        end=match.end(),
                        quote=quote,
                    ),
                    confidence=0.95,
                ),
                [source_name, target_name],
            )


def rule_based_extract(chunk: TextChunk, result: ExtractionResult) -> ExtractionResult:
    entities = list(result.entities)
    facts = list(result.facts)
    entity_names = _existing_entity_names(result)
    fact_keys = _existing_fact_keys(result)

    for fact, names in _rule_facts(chunk):
        for name in names:
            if name not in entity_names:
                entities.append(_entity(name))
                entity_names.add(name)
        key = (
            fact.relation,
            fact.source_local_id,
            fact.target_local_id,
            fact.evidence.quote,
        )
        if key not in fact_keys:
            facts.append(fact)
            fact_keys.add(key)

    return ExtractionResult(entities=entities, facts=facts)
