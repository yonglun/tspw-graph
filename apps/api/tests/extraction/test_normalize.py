from app.extraction.models import ExtractionResult
from app.extraction.normalize import normalize_chunk_result
from app.extraction.splitter import TextChunk


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
