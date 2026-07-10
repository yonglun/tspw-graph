from app.extraction.fixed import FixedProvider
from app.extraction.models import ExtractionResult
from app.extraction.pipeline import ExtractionPipeline
from app.graph.models import ImportSummary


class CapturingImporter:
    def __init__(self):
        self.document = None

    def import_document(self, document):
        self.document = document
        attribute_evidence = {
            evidence_id
            for attribute in document.attributes
            for evidence_id in attribute.evidence_ids
        }
        return ImportSummary(
            retained_attributes=len(document.attributes),
            retained_attribute_evidence=len(attribute_evidence),
            retained_evidence=len(document.evidence),
        )


def test_pipeline_aggregates_attribute_evidence_and_reports_quality():
    source = "第一章 开端\n令狐冲是华山派大弟子。令狐冲乃华山派大弟子。"

    class AttributeProvider:
        def extract(self, request):
            value = "华山派大弟子"
            first_start = request.text.find(value)
            second_start = request.text.find(value, first_start + len(value))
            return ExtractionResult.model_validate({
                "entities": [
                    {"local_id": "p1", "name": "令狐冲", "type": "Person"}
                ],
                "facts": [],
                "attributes": [
                    {
                        "entity_local_id": "p1",
                        "property_id": "identity",
                        "value": value,
                        "evidence": {
                            "start": first_start,
                            "end": first_start + len(value),
                            "quote": value,
                        },
                    },
                    {
                        "entity_local_id": "p1",
                        "property_id": "identity",
                        "value": value,
                        "evidence": {
                            "start": second_start,
                            "end": second_start + len(value),
                            "quote": value,
                        },
                    },
                ],
            })

    importer = CapturingImporter()
    output = ExtractionPipeline(importer).process(
        "p-1", "测试", source, AttributeProvider()
    )

    assert output.quality.accepted_attributes == 1
    assert output.quality.accepted_attribute_evidence == 2
    assert output.quality.accepted_evidence == 2
    assert output.quality.rejected_by_code == {}
    assert importer.document.attributes[0].property_id == "identity"
    assert len(importer.document.attributes[0].evidence_ids) == 2


def test_pipeline_deduplicates_attribute_evidence_from_overlapping_chunks():
    phrase = "令狐冲是华山派大弟子"
    source = f"{'甲' * 3800}{phrase}{'乙' * 300}"

    class OverlapProvider:
        def extract(self, request):
            phrase_start = request.text.find(phrase)
            if phrase_start < 0:
                return ExtractionResult()
            value = "华山派大弟子"
            value_start = phrase_start + len("令狐冲是")
            return ExtractionResult.model_validate({
                "entities": [
                    {"local_id": "p1", "name": "令狐冲", "type": "Person"}
                ],
                "facts": [],
                "attributes": [{
                    "entity_local_id": "p1",
                    "property_id": "identity",
                    "value": value,
                    "evidence": {
                        "start": value_start,
                        "end": value_start + len(value),
                        "quote": value,
                    },
                }],
            })

    importer = CapturingImporter()
    output = ExtractionPipeline(importer).process(
        "p-1", "测试", source, OverlapProvider()
    )

    assert output.quality.total_chunks == 2
    assert output.quality.accepted_attributes == 1
    assert output.quality.accepted_evidence == 1
    assert output.quality.accepted_attribute_evidence == 1
    assert len(importer.document.attributes) == 1
    assert len(importer.document.evidence) == 1
    assert len(importer.document.attributes[0].evidence_ids) == 1


def test_overlong_attribute_evidence_does_not_drop_valid_siblings():
    long_quote = "甲" * 501
    source = f"第一章 开端\n令狐冲男{long_quote}"
    valid_start = source.find("男")
    long_start = source.find(long_quote)
    result = ExtractionResult.model_validate({
        "entities": [{"local_id": "p1", "name": "令狐冲", "type": "Person"}],
        "facts": [],
        "attributes": [
            {
                "entity_local_id": "p1", "property_id": "gender", "value": "男",
                "evidence": {"start": valid_start, "end": valid_start + 1, "quote": "男"},
            },
            {
                "entity_local_id": "p1", "property_id": "identity", "value": "大弟子",
                "evidence": {
                    "start": long_start, "end": long_start + len(long_quote),
                    "quote": long_quote,
                },
            },
        ],
    })
    importer = CapturingImporter()

    output = ExtractionPipeline(importer).process(
        "p-1", "测试", source, FixedProvider(result)
    )

    assert output.quality.accepted_entities == 1
    assert output.quality.accepted_attributes == 1
    assert output.quality.accepted_attribute_evidence == 1
    assert output.quality.rejected_by_code == {"ATTRIBUTE_EVIDENCE_TOO_LONG": 1}
    assert len(importer.document.attributes) == 1
