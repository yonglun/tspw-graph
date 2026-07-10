from app.extraction.models import ExtractionResult
from app.extraction.normalize import normalize_chunk_result
from app.extraction.splitter import TextChunk
from app.ontology.models import PropertyDefinition, PropertyValueType


def test_normalizer_rejects_unknown_type():
    chunk = TextChunk("c1", 1, 10, 14, "某人出现")
    result = ExtractionResult.model_validate({
        "entities": [{"local_id": "x", "name": "某人", "type": "Unknown"}],
        "facts": [],
    })
    normalized = normalize_chunk_result("p-1", chunk, result)
    assert normalized.entities == []
    assert normalized.rejections[0].code == "UNKNOWN_ENTITY_TYPE"


def test_normalizer_converts_evidence_to_absolute_offsets():
    chunk = TextChunk("c1", 1, 100, 103, "甲识乙")
    result = ExtractionResult.model_validate({
        "entities": [
            {"local_id": "a", "name": "甲", "type": "Person"},
            {"local_id": "b", "name": "乙", "type": "Person"},
        ],
        "facts": [{
            "relation": "ALLY_OF", "source_local_id": "a", "target_local_id": "b",
            "evidence": {"start": 0, "end": 3, "quote": "甲识乙"}
        }],
    })
    normalized = normalize_chunk_result("p-1", chunk, result)
    assert normalized.evidence[0].start_offset == 100
    assert normalized.evidence[0].end_offset == 103
    assert normalized.facts[0].evidence_ids == [normalized.evidence[0].id]


def test_normalizer_realigns_evidence_quote_when_offsets_are_wrong():
    chunk = TextChunk("c1", 1, 100, 108, "前文甲识乙")
    result = ExtractionResult.model_validate({
        "entities": [
            {"local_id": "a", "name": "甲", "type": "Person"},
            {"local_id": "b", "name": "乙", "type": "Person"},
        ],
        "facts": [{
            "relation": "ALLY_OF", "source_local_id": "a", "target_local_id": "b",
            "evidence": {"start": 0, "end": 3, "quote": "甲识乙"}
        }],
    })
    normalized = normalize_chunk_result("p-1", chunk, result)
    assert normalized.rejections == []
    assert normalized.evidence[0].start_offset == 102
    assert normalized.evidence[0].end_offset == 105
    assert normalized.facts[0].evidence_ids == [normalized.evidence[0].id]


def test_normalizer_rejects_unmatched_evidence_without_failing_chunk():
    chunk = TextChunk("c1", 1, 100, 103, "甲识乙")
    result = ExtractionResult.model_validate({
        "entities": [
            {"local_id": "a", "name": "甲", "type": "Person"},
            {"local_id": "b", "name": "乙", "type": "Person"},
        ],
        "facts": [{
            "relation": "ALLY_OF", "source_local_id": "a", "target_local_id": "b",
            "evidence": {"start": 0, "end": 3, "quote": "不存在"}
        }],
    })
    normalized = normalize_chunk_result("p-1", chunk, result)
    assert normalized.facts == []
    assert normalized.evidence == []
    assert normalized.rejections[0].code == "EVIDENCE_MISMATCH"


def test_normalizer_rejects_empty_evidence_without_failing_chunk():
    chunk = TextChunk("c1", 1, 100, 103, "甲识乙")
    result = ExtractionResult.model_validate({
        "entities": [
            {"local_id": "a", "name": "甲", "type": "Person"},
            {"local_id": "b", "name": "乙", "type": "Person"},
        ],
        "facts": [{
            "relation": "ALLY_OF", "source_local_id": "a", "target_local_id": "b",
            "evidence": {"start": 0, "end": 0, "quote": ""}
        }],
    })
    normalized = normalize_chunk_result("p-1", chunk, result)
    assert normalized.facts == []
    assert normalized.evidence == []
    assert normalized.rejections[0].code == "EVIDENCE_MISMATCH"


def test_normalizer_rejects_overlong_evidence_without_failing_chunk():
    long_quote = "甲识乙" * 200
    chunk = TextChunk("c1", 1, 100, 100 + len(long_quote), long_quote)
    result = ExtractionResult.model_validate({
        "entities": [
            {"local_id": "a", "name": "甲", "type": "Person"},
            {"local_id": "b", "name": "乙", "type": "Person"},
        ],
        "facts": [{
            "relation": "ALLY_OF", "source_local_id": "a", "target_local_id": "b",
            "evidence": {"start": 0, "end": len(long_quote), "quote": long_quote}
        }],
    })
    normalized = normalize_chunk_result("p-1", chunk, result)
    assert normalized.facts == []
    assert normalized.evidence == []
    assert normalized.rejections[0].code == "EVIDENCE_TOO_LONG"


def test_normalizer_rejects_blank_fact_endpoint_without_failing_chunk():
    chunk = TextChunk("c1", 1, 100, 103, "甲识乙")
    result = ExtractionResult.model_validate({
        "entities": [
            {"local_id": "a", "name": "甲", "type": "Person"},
            {"local_id": "b", "name": "乙", "type": "Person"},
        ],
        "facts": [{
            "relation": "ALLY_OF", "source_local_id": "", "target_local_id": "b",
            "evidence": {"start": 0, "end": 3, "quote": "甲识乙"}
        }],
    })
    normalized = normalize_chunk_result("p-1", chunk, result)
    assert normalized.facts == []
    assert normalized.evidence == []
    assert normalized.rejections[0].code == "UNKNOWN_FACT_ENTITY"


def test_normalizer_rejects_blank_entity_name_without_failing_chunk():
    chunk = TextChunk("c1", 1, 100, 103, "甲识乙")
    result = ExtractionResult.model_validate({
        "entities": [
            {"local_id": "a", "name": "", "type": "Person"},
            {"local_id": "b", "name": "乙", "type": "Person"},
        ],
        "facts": [{
            "relation": "ALLY_OF", "source_local_id": "a", "target_local_id": "b",
            "evidence": {"start": 0, "end": 3, "quote": "甲识乙"}
        }],
    })
    normalized = normalize_chunk_result("p-1", chunk, result)
    assert [entity.name for entity in normalized.entities] == ["乙"]
    assert normalized.facts == []
    assert normalized.evidence == []
    assert [rejection.code for rejection in normalized.rejections] == [
        "EMPTY_ENTITY_NAME",
        "UNKNOWN_FACT_ENTITY",
    ]


def test_normalizer_creates_stable_evidence_backed_attribute():
    chunk = TextChunk("c1", 1, 100, 106, "华山派大弟子")
    result = ExtractionResult.model_validate({
        "entities": [
            {
                "local_id": "p1",
                "name": "令狐冲",
                "type": "Person",
                "aliases": [],
            }
        ],
        "facts": [],
        "attributes": [{
            "entity_local_id": "p1",
            "property_id": "identity",
            "value": " 华山派大弟子 ",
            "evidence": {"start": 0, "end": 6, "quote": "华山派大弟子"},
            "confidence": 0.96,
        }],
    })

    normalized = normalize_chunk_result("p-1", chunk, result)

    assert normalized.attributes[0].entity_id == normalized.entities[0].id
    assert normalized.attributes[0].entity_name == "令狐冲"
    assert normalized.attributes[0].value == "华山派大弟子"
    assert normalized.attributes[0].value_type == PropertyValueType.TEXT
    assert normalized.attributes[0].evidence_ids == [normalized.evidence[0].id]
    assert normalized.evidence[0].start_offset == 100


def test_invalid_attribute_is_rejected_without_dropping_entity():
    chunk = TextChunk("c1", 1, 0, 3, "令狐冲")
    result = ExtractionResult.model_validate({
        "entities": [
            {
                "local_id": "p1",
                "name": "令狐冲",
                "type": "Person",
                "aliases": [],
            }
        ],
        "facts": [],
        "attributes": [{
            "entity_local_id": "p1",
            "property_id": "master",
            "value": "岳不群",
            "evidence": {"start": 0, "end": 3, "quote": "令狐冲"},
            "confidence": 0.9,
        }],
    })

    normalized = normalize_chunk_result("p-1", chunk, result)

    assert normalized.entities
    assert normalized.attributes == []
    assert [item.code for item in normalized.rejections] == [
        "UNKNOWN_ENTITY_PROPERTY"
    ]


def test_attribute_rejections_are_granular(monkeypatch):
    definitions = {
        "score": PropertyDefinition(
            id="score", label="分数", description="", value_type=PropertyValueType.NUMBER
        ),
        "active": PropertyDefinition(
            id="active", label="有效", description="", value_type=PropertyValueType.BOOLEAN
        ),
    }
    monkeypatch.setattr(
        "app.extraction.normalize.property_definition_for",
        lambda _entity_type, property_id: definitions.get(property_id),
    )
    chunk = TextChunk("c1", 1, 0, 8, "令狐冲甲乙丙丁戊")

    def rejection_code(attribute):
        result = ExtractionResult.model_validate({
            "entities": [{"local_id": "p1", "name": "令狐冲", "type": "Person"}],
            "facts": [],
            "attributes": [attribute],
        })
        return normalize_chunk_result("p-1", chunk, result).rejections[0].code

    evidence = {"start": 0, "end": 3, "quote": "令狐冲"}
    assert rejection_code({
        "entity_local_id": "p1", "property_id": "score", "value": " ",
        "evidence": evidence,
    }) == "EMPTY_ATTRIBUTE_VALUE"
    assert rejection_code({
        "entity_local_id": "missing", "property_id": "score", "value": "1",
        "evidence": evidence,
    }) == "UNKNOWN_ATTRIBUTE_ENTITY"
    assert rejection_code({
        "entity_local_id": "p1", "property_id": "score", "value": "many",
        "evidence": evidence,
    }) == "INVALID_ATTRIBUTE_NUMBER"
    assert rejection_code({
        "entity_local_id": "p1", "property_id": "active", "value": "maybe",
        "evidence": evidence,
    }) == "INVALID_ATTRIBUTE_BOOLEAN"


def test_attribute_number_and_boolean_values_are_canonicalized(monkeypatch):
    definitions = {
        "score": PropertyDefinition(
            id="score", label="分数", description="", value_type=PropertyValueType.NUMBER
        ),
        "active": PropertyDefinition(
            id="active", label="有效", description="", value_type=PropertyValueType.BOOLEAN
        ),
    }
    monkeypatch.setattr(
        "app.extraction.normalize.property_definition_for",
        lambda _entity_type, property_id: definitions.get(property_id),
    )
    chunk = TextChunk("c1", 1, 0, 5, "1.00真")
    result = ExtractionResult.model_validate({
        "entities": [{"local_id": "p1", "name": "令狐冲", "type": "Person"}],
        "facts": [],
        "attributes": [
            {
                "entity_local_id": "p1", "property_id": "score", "value": "1.00",
                "evidence": {"start": 0, "end": 4, "quote": "1.00"},
            },
            {
                "entity_local_id": "p1", "property_id": "active", "value": "TRUE",
                "evidence": {"start": 4, "end": 5, "quote": "真"},
            },
        ],
    })

    normalized = normalize_chunk_result("p-1", chunk, result)

    assert [attribute.value for attribute in normalized.attributes] == ["1", "true"]


def test_attribute_rejects_invalid_enum_and_evidence_individually():
    chunk = TextChunk("c1", 1, 0, 4, "令狐冲男")

    def rejection_code(value, evidence):
        result = ExtractionResult.model_validate({
            "entities": [{"local_id": "p1", "name": "令狐冲", "type": "Person"}],
            "facts": [],
            "attributes": [{
                "entity_local_id": "p1", "property_id": "gender", "value": value,
                "evidence": evidence,
            }],
        })
        return normalize_chunk_result("p-1", chunk, result).rejections[0].code

    assert rejection_code("未知", {"start": 3, "end": 4, "quote": "男"}) == (
        "INVALID_ATTRIBUTE_ENUM"
    )
    assert rejection_code("男", {"start": 0, "end": 1, "quote": "不存在"}) == (
        "ATTRIBUTE_EVIDENCE_MISMATCH"
    )

    long_quote = "男" * 501
    long_chunk = TextChunk("c2", 1, 0, len(long_quote), long_quote)
    result = ExtractionResult.model_validate({
        "entities": [{"local_id": "p1", "name": "令狐冲", "type": "Person"}],
        "facts": [],
        "attributes": [{
            "entity_local_id": "p1", "property_id": "gender", "value": "男",
            "evidence": {"start": 0, "end": len(long_quote), "quote": long_quote},
        }],
    })
    normalized = normalize_chunk_result("p-1", long_chunk, result)
    assert normalized.attributes == []
    assert normalized.evidence == []
    assert normalized.rejections[0].code == "ATTRIBUTE_EVIDENCE_TOO_LONG"
