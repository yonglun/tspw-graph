from app.extraction.models import ExtractionResult
from app.extraction.rules import rule_based_extract
from app.extraction.splitter import TextChunk


def test_rule_based_extracts_master_and_spouse_relations_with_exact_evidence():
    text = "令狐冲的师父是岳不群。岳夫人是岳不群的妻子。"
    result = rule_based_extract(
        TextChunk(
            id="chapter-1-chunk-1",
            chapter_number=1,
            start_offset=0,
            end_offset=len(text),
            text=text,
        ),
        ExtractionResult(entities=[], facts=[]),
    )

    facts = {(fact.relation, fact.source_local_id, fact.target_local_id) for fact in result.facts}
    assert ("MASTER_OF", "rule_person_岳不群", "rule_person_令狐冲") in facts
    assert ("SPOUSE_OF", "rule_person_岳夫人", "rule_person_岳不群") in facts
    for fact in result.facts:
        assert text[fact.evidence.start : fact.evidence.end] == fact.evidence.quote
