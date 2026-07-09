import pytest
from pydantic import ValidationError

from app.extraction.models import ExtractionResult


def test_extraction_result_rejects_excessive_entities():
    payload = {
        "entities": [
            {"local_id": f"e-{i}", "name": str(i), "type": "Person"}
            for i in range(101)
        ],
        "facts": [],
    }
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(payload)


def test_extraction_result_accepts_model_generated_local_ids_with_chinese():
    result = ExtractionResult.model_validate(
        {
            "entities": [
                {
                    "local_id": "entity_person_令狐冲",
                    "name": "令狐冲",
                    "type": "Person",
                    "aliases": [],
                }
            ],
            "facts": [
                {
                    "relation": "KNOWS",
                    "source_local_id": "entity_person_令狐冲",
                    "target_local_id": "entity_person_岳灵珊",
                    "evidence": {"start": 0, "end": 3, "quote": "令狐冲"},
                    "confidence": 0.9,
                }
            ],
        }
    )
    assert result.entities[0].local_id == "entity_person_令狐冲"
    assert result.facts[0].source_local_id == "entity_person_令狐冲"


def test_extraction_result_accepts_empty_model_evidence_for_downstream_rejection():
    result = ExtractionResult.model_validate(
        {
            "entities": [],
            "facts": [
                {
                    "relation": "KNOWS",
                    "source_local_id": "a",
                    "target_local_id": "b",
                    "evidence": {"start": 0, "end": 0, "quote": ""},
                    "confidence": 0.5,
                }
            ],
        }
    )
    assert result.facts[0].evidence.end == 0
    assert result.facts[0].evidence.quote == ""


def test_extraction_result_accepts_overlong_model_evidence_for_downstream_rejection():
    long_quote = "令狐冲" * 200
    result = ExtractionResult.model_validate(
        {
            "entities": [],
            "facts": [
                {
                    "relation": "KNOWS",
                    "source_local_id": "a",
                    "target_local_id": "b",
                    "evidence": {
                        "start": 0,
                        "end": len(long_quote),
                        "quote": long_quote,
                    },
                    "confidence": 0.5,
                }
            ],
        }
    )
    assert result.facts[0].evidence.quote == long_quote


def test_evidence_offsets_and_quote_must_match_chunk():
    result = ExtractionResult.model_validate(
        {
            "entities": [],
            "facts": [
                {
                    "relation": "KNOWS",
                    "source_local_id": "a",
                    "target_local_id": "b",
                    "evidence": {"start": 0, "end": 2, "quote": "错误"},
                }
            ],
        }
    )
    with pytest.raises(ValueError, match="EVIDENCE_QUOTE_MISMATCH"):
        result.validate_for_chunk("正确")
