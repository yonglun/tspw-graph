from app.extraction.fixed import FixedProvider
from app.extraction.models import ExtractionResult
from app.extraction.pipeline import ExtractionPipeline
from app.extraction.providers import ProviderError, ProviderErrorKind
from app.graph.importer import GraphImporter


class MemoryWriter:
    def __init__(self):
        self.keys = {"Entity": set(), "Fact": set(), "Evidence": set()}
    def ensure_constraints(self): pass
    def upsert_batch(self, label, rows):
        if label not in self.keys: return 0
        before = len(self.keys[label])
        self.keys[label].update(row["id"] for row in rows)
        return len(self.keys[label]) - before


class CapturingWriter(MemoryWriter):
    def __init__(self):
        super().__init__()
        self.rows = {"Entity": [], "Fact": [], "Evidence": []}

    def upsert_batch(self, label, rows):
        if label in self.rows:
            self.rows[label].extend(rows)
        return super().upsert_batch(label, rows)


class EmptyProvider:
    def extract(self, request):
        return ExtractionResult(entities=[], facts=[])


def test_pipeline_sends_effective_property_definitions_to_provider():
    class CapturingProvider:
        def __init__(self):
            self.ontology = None

        def extract(self, request):
            self.ontology = request.ontology
            return ExtractionResult()

    provider = CapturingProvider()
    pipeline = ExtractionPipeline(GraphImporter(MemoryWriter()))

    pipeline.process("p-1", "测试", "第一章 开端\n正文", provider)

    sect_property_ids = {
        item["id"] for item in provider.ontology["property_definitions"]["Sect"]
    }
    assert {"characteristic", "activity_region"} <= sect_property_ids


def test_fixed_provider_pipeline_is_idempotent():
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
    writer = MemoryWriter()
    pipeline = ExtractionPipeline(GraphImporter(writer))
    first = pipeline.process("p-1", "测试", "第一章 开端\n甲识乙", FixedProvider(result))
    second = pipeline.process("p-1", "测试", "第一章 开端\n甲识乙", FixedProvider(result))
    assert first.quality.accepted_facts == 1
    assert first.import_summary.created_facts == 1
    assert second.import_summary.created_facts == 0


def test_pipeline_adds_rule_based_master_and_spouse_facts():
    writer = CapturingWriter()
    pipeline = ExtractionPipeline(GraphImporter(writer))
    output = pipeline.process(
        "p-1",
        "测试",
        "第一章 正文\n令狐冲的师父是岳不群。岳夫人是岳不群的妻子。",
        EmptyProvider(),
    )

    fact_types = {row["type"] for row in writer.rows["Fact"]}
    assert {"MASTER_OF", "SPOUSE_OF"} <= fact_types
    assert output.quality.accepted_facts == 2
    assert output.quality.accepted_entities == 3


def test_pipeline_realigns_model_evidence_offsets():
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
    writer = MemoryWriter()
    pipeline = ExtractionPipeline(GraphImporter(writer))
    output = pipeline.process("p-1", "测试", "第一章 开端\n前文甲识乙", FixedProvider(result))
    assert output.quality.accepted_facts == 1
    assert output.quality.rejected_by_code == {}


def test_pipeline_skips_content_filtered_chunks():
    class ContentFilterProvider:
        def extract(self, request):
            raise ProviderError(ProviderErrorKind.INVALID_RESPONSE, "MODEL_CONTENT_FILTER")

    writer = MemoryWriter()
    pipeline = ExtractionPipeline(GraphImporter(writer))
    output = pipeline.process("p-1", "测试", "第一章 开端\n甲识乙", ContentFilterProvider())

    assert output.quality.total_chunks == 1
    assert output.quality.successful_chunks == 0
    assert output.quality.failed_chunks == 1
    assert output.quality.rejected_by_code == {"MODEL_CONTENT_FILTER": 1}
    assert output.quality.accepted_facts == 0


def test_pipeline_retries_retryable_provider_errors():
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

    class FlakyProvider:
        def __init__(self):
            self.calls = 0

        def extract(self, request):
            self.calls += 1
            if self.calls == 1:
                raise ProviderError(
                    ProviderErrorKind.RETRYABLE,
                    "MODEL_HTTP_429",
                    retry_after_seconds=1.2,
                )
            return result

    sleeps = []
    provider = FlakyProvider()
    writer = MemoryWriter()
    pipeline = ExtractionPipeline(GraphImporter(writer), retry_sleep=sleeps.append)
    output = pipeline.process("p-1", "测试", "第一章 开端\n甲识乙", provider)

    assert provider.calls == 2
    assert sleeps == [1.2]
    assert output.quality.retry_count == 1
    assert output.quality.successful_chunks == 1
