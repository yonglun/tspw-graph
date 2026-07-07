from app.review.models import ReviewItemType
from app.review.rules import FactCandidate, RuleScanner


def test_rule_scanner_flags_low_confidence_missing_evidence_and_duplicates():
    scanner = RuleScanner(low_confidence_threshold=0.65)
    items = scanner.scan_candidates(
        project_id="project-a",
        facts=[
            FactCandidate(
                id="fact-low",
                type="ALLY_OF",
                source_id="linghu",
                target_id="ren",
                confidence=0.4,
                evidence_ids=["ev-1"],
                source_type="Person",
                target_type="Person",
            ),
            FactCandidate(
                id="fact-no-evidence",
                type="MASTER_OF",
                source_id="feng",
                target_id="linghu",
                confidence=0.9,
                evidence_ids=[],
                source_type="Person",
                target_type="Person",
            ),
        ],
        entities=[
            {"id": "e-1", "name": "令狐冲", "aliases": ["令狐少侠"], "type": "Person"},
            {"id": "e-2", "name": "令狐冲", "aliases": [], "type": "Person"},
        ],
    )

    assert {item.reason_code for item in items} >= {
        "LOW_CONFIDENCE_FACT",
        "MISSING_EVIDENCE",
        "POSSIBLE_DUPLICATE_ENTITY",
    }
    duplicate = next(item for item in items if item.reason_code == "POSSIBLE_DUPLICATE_ENTITY")
    assert duplicate.item_type == ReviewItemType.DUPLICATE_ENTITY


def test_rule_scanner_produces_three_review_item_types():
    scanner = RuleScanner(low_confidence_threshold=0.65)
    items = scanner.scan_candidates(
        project_id="project-a",
        facts=[
            FactCandidate(
                id="fact-low",
                type="ALLY_OF",
                source_id="e-1",
                target_id="e-2",
                confidence=0.4,
                evidence_ids=["ev-1"],
                source_type="Person",
                target_type="Person",
            ),
            FactCandidate(
                id="fact-missing",
                type="MASTER_OF",
                source_id="e-1",
                target_id="e-2",
                confidence=0.9,
                evidence_ids=[],
                source_type="Person",
                target_type="Person",
            ),
        ],
        entities=[
            {"id": "e-1", "name": "令狐冲", "aliases": [], "type": "Person"},
            {"id": "e-2", "name": "令狐冲", "aliases": [], "type": "Person"},
        ],
    )

    assert {
        "LOW_CONFIDENCE_FACT",
        "MISSING_EVIDENCE",
        "POSSIBLE_DUPLICATE_ENTITY",
    } <= {item.reason_code for item in items}
