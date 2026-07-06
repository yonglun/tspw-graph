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
