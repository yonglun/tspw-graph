import pytest
from pydantic import ValidationError

from app.extraction.models import ExtractionResult, strict_extraction_schema


def test_extraction_result_accepts_evidence_backed_attribute():
    result = ExtractionResult.model_validate(
        {
            "entities": [
                {
                    "local_id": "p1",
                    "name": "令狐冲",
                    "type": "Person",
                    "aliases": [],
                }
            ],
            "facts": [],
            "attributes": [
                {
                    "entity_local_id": "p1",
                    "property_id": "identity",
                    "value": "华山派大弟子",
                    "evidence": {"start": 0, "end": 6, "quote": "华山派大弟子"},
                    "confidence": 0.96,
                }
            ],
        }
    )

    assert result.attributes[0].property_id == "identity"


def test_strict_schema_requires_attributes_at_root():
    schema = strict_extraction_schema()

    assert schema["required"] == ["entities", "facts", "attributes"]
    assert schema["properties"]["attributes"]["items"]["additionalProperties"] is False


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


def test_extraction_result_accepts_overlong_attribute_evidence_for_downstream_rejection():
    long_quote = "华山派大弟子" * 100
    result = ExtractionResult.model_validate(
        {
            "entities": [],
            "facts": [],
            "attributes": [
                {
                    "entity_local_id": "p1",
                    "property_id": "identity",
                    "value": "华山派大弟子",
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

    assert result.attributes[0].evidence.quote == long_quote


def test_extraction_result_accepts_blank_entity_fields_for_downstream_rejection():
    result = ExtractionResult.model_validate(
        {
            "entities": [
                {"local_id": "a", "name": "", "type": "Person", "aliases": []},
                {"local_id": "", "name": "乙", "type": "Person", "aliases": []},
                {"local_id": "c", "name": "丙", "type": "", "aliases": []},
            ],
            "facts": [
                {
                    "relation": "",
                    "source_local_id": "a",
                    "target_local_id": "b",
                    "evidence": {"start": 0, "end": 1, "quote": "甲"},
                    "confidence": 0.5,
                }
            ],
        }
    )
    assert result.entities[0].name == ""
    assert result.entities[1].local_id == ""
    assert result.entities[2].type == ""
    assert result.facts[0].relation == ""


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


def test_attribute_evidence_offsets_and_quote_must_match_chunk():
    result = ExtractionResult.model_validate(
        {
            "entities": [],
            "facts": [],
            "attributes": [
                {
                    "entity_local_id": "p1",
                    "property_id": "identity",
                    "value": "大弟子",
                    "evidence": {"start": 0, "end": 3, "quote": "大弟子"},
                    "confidence": 0.9,
                }
            ],
        }
    )

    with pytest.raises(ValueError, match="EVIDENCE_QUOTE_MISMATCH"):
        result.validate_for_chunk("掌门人")
