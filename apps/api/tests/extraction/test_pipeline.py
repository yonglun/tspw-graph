from types import SimpleNamespace

import pytest

from app.extraction.fixed import FixedProvider
from app.extraction.models import ExtractionResult
from app.extraction.pipeline import ExtractionPipeline, PipelineCancelled
from app.extraction.providers import ProviderError, ProviderErrorKind
from app.extraction.splitter import TextChunk
from app.graph.importer import GraphImporter, canonicalize_attribute_rows
from app.graph.models import ImportSummary


class MemoryWriter:
    def __init__(self):
        self.keys = {"Entity": set(), "Fact": set(), "Evidence": set()}
    def ensure_constraints(self): pass
    def upsert_batch(self, label, rows):
        if label not in self.keys: return 0
        before = len(self.keys[label])
        self.keys[label].update(row["id"] for row in rows)
        return len(self.keys[label]) - before
    def resolve_attribute_entities(self, project_id, hints):
        return {hint["id"]: hint["id"] for hint in hints if hint["id"] in self.keys["Entity"]}
    def upsert_attribute_bundle(self, project_id, hints, attributes, evidence, protected_evidence_ids):
        resolved = canonicalize_attribute_rows(
            project_id, attributes, self.resolve_attribute_entities(project_id, hints)
        )
        attribute_evidence_ids = {
            evidence_id for attribute in resolved for evidence_id in attribute["evidence_ids"]
        }
        referenced = protected_evidence_ids | attribute_evidence_ids
        evidence_rows = [
            {"project_id": project_id, **row} for row in evidence if row["id"] in referenced
        ]
        return ImportSummary(
            created_evidence=self.upsert_batch("Evidence", evidence_rows),
            created_attributes=self.upsert_batch("AttributeAssertion", resolved),
            retained_attributes=len(resolved),
            retained_attribute_evidence=len(attribute_evidence_ids),
            retained_evidence=len(evidence_rows),
        )


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


def test_pipeline_reports_total_and_each_completed_chunk(monkeypatch):
    chunks = [
        TextChunk(
            id="c-1",
            chapter_number=1,
            start_offset=0,
            end_offset=3,
            text="甲识乙",
        ),
        TextChunk(
            id="c-2",
            chapter_number=1,
            start_offset=3,
            end_offset=6,
            text="丙识丁",
        ),
    ]
    split = SimpleNamespace(chunks=chunks, chapters=[])
    monkeypatch.setattr(
        "app.extraction.pipeline.split_document", lambda _: split
    )
    progress = []

    ExtractionPipeline(GraphImporter(MemoryWriter())).process(
        "p-1",
        "测试",
        "source",
        EmptyProvider(),
        on_progress=lambda completed, total: progress.append(
            (completed, total)
        ),
    )

    assert progress == [(0, 2), (1, 2), (2, 2)]


def test_pipeline_counts_content_filtered_chunks_as_completed():
    class ContentFilterProvider:
        def extract(self, request):
            raise ProviderError(
                ProviderErrorKind.INVALID_RESPONSE,
                "MODEL_CONTENT_FILTER",
            )

    progress = []
    ExtractionPipeline(GraphImporter(MemoryWriter())).process(
        "p-1",
        "测试",
        "第一章 开端\n甲识乙",
        ContentFilterProvider(),
        on_progress=lambda completed, total: progress.append(
            (completed, total)
        ),
    )

    assert progress == [(0, 1), (1, 1)]


def test_pipeline_stops_before_import_when_cancelled_after_a_chunk(
    monkeypatch,
):
    chunks = [
        TextChunk(
            id="c-1",
            chapter_number=1,
            start_offset=0,
            end_offset=3,
            text="甲识乙",
        )
    ]
    split = SimpleNamespace(chunks=chunks, chapters=[])
    monkeypatch.setattr(
        "app.extraction.pipeline.split_document", lambda _: split
    )
    writer = CapturingWriter()
    checks = iter([False, True])

    with pytest.raises(PipelineCancelled, match="JOB_CANCELLED"):
        ExtractionPipeline(GraphImporter(writer)).process(
            "p-1",
            "测试",
            "source",
            EmptyProvider(),
            should_cancel=lambda: next(checks, True),
        )

    assert writer.rows == {"Entity": [], "Fact": [], "Evidence": []}


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


def test_attribute_only_pipeline_imports_only_attribute_evidence():
    source = "第一章 开端\n甲识乙，甲是掌门"
    fact_start = source.find("甲识乙")
    attribute_start = source.find("掌门")
    result = ExtractionResult.model_validate({
        "entities": [
            {"local_id": "a", "name": "甲", "type": "Person"},
            {"local_id": "b", "name": "乙", "type": "Person"},
        ],
        "facts": [{
            "relation": "ALLY_OF",
            "source_local_id": "a",
            "target_local_id": "b",
            "evidence": {
                "start": fact_start,
                "end": fact_start + len("甲识乙"),
                "quote": "甲识乙",
            },
        }],
        "attributes": [{
            "entity_local_id": "a",
            "property_id": "identity",
            "value": "掌门",
            "evidence": {
                "start": attribute_start,
                "end": attribute_start + len("掌门"),
                "quote": "掌门",
            },
        }],
    })

    class RecordingWriter(MemoryWriter):
        def __init__(self):
            super().__init__()
            self.rows = {}

        def ensure_constraints(self):
            pass

        def upsert_batch(self, label, rows):
            self.rows[label] = rows
            return len(rows)

        def resolve_attribute_entities(self, project_id, hints):
            return {hint["id"]: hint["id"] for hint in hints}

    writer = RecordingWriter()
    output = ExtractionPipeline(GraphImporter(writer)).process(
        "p-1", "测试", source, FixedProvider(result), attributes_only=True
    )

    assert set(writer.rows) == {"Evidence", "AttributeAssertion"}
    referenced_evidence = writer.rows["AttributeAssertion"][0]["evidence_ids"]
    assert [row["id"] for row in writer.rows["Evidence"]] == referenced_evidence
    assert output.quality.accepted_entities == 0
    assert output.quality.accepted_facts == 0
    assert output.quality.accepted_evidence == 1
    assert output.import_summary.created_entities == 0
    assert output.import_summary.created_facts == 0
    assert output.import_summary.created_evidence == 1
    assert output.import_summary.created_attributes == 1


def test_attribute_only_quality_counts_only_resolved_assertions_and_evidence():
    source = "第一章 开端\n甲是掌门"
    value_start = source.find("掌门")
    result = ExtractionResult.model_validate({
        "entities": [{"local_id": "a", "name": "甲", "type": "Person"}],
        "attributes": [{
            "entity_local_id": "a",
            "property_id": "identity",
            "value": "掌门",
            "evidence": {
                "start": value_start,
                "end": value_start + len("掌门"),
                "quote": "掌门",
            },
        }],
    })

    class RejectingWriter(MemoryWriter):
        def resolve_attribute_entities(self, project_id, hints):
            return {}

    output = ExtractionPipeline(GraphImporter(RejectingWriter())).process(
        "p-1", "测试", source, FixedProvider(result), attributes_only=True
    )

    assert output.quality.accepted_attributes == 0
    assert output.quality.accepted_attribute_evidence == 0
    assert output.quality.accepted_evidence == 0
    assert output.import_summary.created_attributes == 0
    assert output.import_summary.created_evidence == 0
