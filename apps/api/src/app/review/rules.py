from dataclasses import dataclass
from typing import Any

from app.ontology.catalog import relation_by_id
from app.review.models import ReviewItemCreate, ReviewItemType, ReviewSource


@dataclass(frozen=True)
class FactCandidate:
    id: str
    type: str
    source_id: str
    target_id: str
    confidence: float
    evidence_ids: list[str]
    source_type: str
    target_type: str


class RuleScanner:
    def __init__(self, low_confidence_threshold: float = 0.65) -> None:
        self.low_confidence_threshold = low_confidence_threshold

    def scan_candidates(
        self,
        project_id: str,
        facts: list[FactCandidate],
        entities: list[dict[str, Any]],
    ) -> list[ReviewItemCreate]:
        items: list[ReviewItemCreate] = []
        for fact in facts:
            if fact.confidence < self.low_confidence_threshold:
                items.append(self._fact_item(fact, "LOW_CONFIDENCE_FACT", 40))
            if not fact.evidence_ids:
                items.append(self._fact_item(fact, "MISSING_EVIDENCE", 70))
            relation = relation_by_id(fact.type)
            if relation and (
                fact.source_type not in relation.source_types
                or fact.target_type not in relation.target_types
            ):
                items.append(self._fact_item(fact, "ONTOLOGY_VIOLATION", 95))
        items.extend(self._duplicate_entity_items(entities))
        return items

    def _fact_item(
        self, fact: FactCandidate, reason_code: str, severity: int
    ) -> ReviewItemCreate:
        return ReviewItemCreate(
            item_type=ReviewItemType.FACT,
            source=ReviewSource.RULE,
            reason_code=reason_code,
            target={"fact_id": fact.id},
            evidence_ids=fact.evidence_ids,
            fingerprint=f"fact:{fact.id}:{reason_code}",
            severity=severity,
        )

    def _duplicate_entity_items(
        self, entities: list[dict[str, Any]]
    ) -> list[ReviewItemCreate]:
        by_name: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for entity in entities:
            by_name.setdefault(
                (entity["type"], entity["name"].strip().lower()), []
            ).append(entity)
        items: list[ReviewItemCreate] = []
        for group in by_name.values():
            if len(group) < 2:
                continue
            source, target = sorted(group, key=lambda row: row["id"])[:2]
            items.append(
                ReviewItemCreate(
                    item_type=ReviewItemType.DUPLICATE_ENTITY,
                    source=ReviewSource.RULE,
                    reason_code="POSSIBLE_DUPLICATE_ENTITY",
                    target={
                        "source_entity_id": source["id"],
                        "target_entity_id": target["id"],
                    },
                    evidence_ids=[],
                    fingerprint=f"duplicate:{source['id']}:{target['id']}",
                    severity=60,
                )
            )
        return items
