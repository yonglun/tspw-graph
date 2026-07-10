from collections import Counter
from collections.abc import Callable
import time

from pydantic import BaseModel, Field

from app.extraction.models import ExtractionRequest, ExtractionResult
from app.extraction.normalize import normalize_chunk_result
from app.extraction.providers import (
    ExtractionProvider,
    ProviderError,
    ProviderErrorKind,
)
from app.extraction.rules import rule_based_extract
from app.extraction.splitter import split_document
from app.graph.importer import GraphImporter
from app.graph.models import (
    AttributeAssertionRecord, ChapterRecord, EntityRecord, EvidenceRecord,
    FactRecord, GraphDocument, ImportSummary, ProjectRecord,
)
from app.ontology.catalog import CATALOG


class QualityReport(BaseModel):
    total_chunks: int
    successful_chunks: int
    failed_chunks: int = 0
    accepted_entities: int
    accepted_facts: int
    accepted_evidence: int
    accepted_attributes: int = 0
    accepted_attribute_evidence: int = 0
    ambiguous_entities: int = 0
    rejected_by_code: dict[str, int] = Field(default_factory=dict)
    model_calls: int
    retry_count: int = 0


class PipelineResult(BaseModel):
    quality: QualityReport
    import_summary: ImportSummary


class ExtractionPipeline:
    def __init__(
        self,
        importer: GraphImporter,
        *,
        max_retries: int = 3,
        retry_backoff_seconds: float = 5.0,
        retry_sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.importer = importer
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.retry_sleep = retry_sleep

    def _retry_delay(self, error: ProviderError, retry_number: int) -> float:
        if error.retry_after_seconds is not None:
            return error.retry_after_seconds
        return min(60.0, self.retry_backoff_seconds * (2 ** (retry_number - 1)))

    def _extract_with_retries(
        self,
        provider: ExtractionProvider,
        request: ExtractionRequest,
    ) -> tuple[ExtractionResult, int]:
        retries = 0
        while True:
            try:
                return provider.extract(request), retries
            except ProviderError as error:
                if error.kind != ProviderErrorKind.RETRYABLE or retries >= self.max_retries:
                    raise
                retries += 1
                self.retry_sleep(self._retry_delay(error, retries))

    def process(
        self,
        project_id: str,
        title: str,
        source: str,
        provider: ExtractionProvider,
    ) -> PipelineResult:
        split = split_document(source)
        entities: dict[str, EntityRecord] = {}
        evidence: dict[str, EvidenceRecord] = {}
        facts: dict[str, FactRecord] = {}
        attributes: dict[str, AttributeAssertionRecord] = {}
        rejections: Counter[str] = Counter()
        failed_chunks = 0
        successful_chunks = 0
        retry_count = 0
        for chunk in split.chunks:
            try:
                extracted, retries = self._extract_with_retries(
                    provider,
                    ExtractionRequest(
                        project_id=project_id,
                        chunk_id=chunk.id,
                        text=chunk.text,
                        ontology={
                            "entity_types": [
                                item.id.value for item in CATALOG.entity_types
                            ],
                            "relation_types": [
                                item.id.value for item in CATALOG.relation_types
                            ],
                            "property_definitions": {
                                item.id.value: [
                                    definition.model_dump(mode="json")
                                    for definition in item.effective_property_definitions
                                ]
                                for item in CATALOG.entity_types
                            },
                        },
                    ),
                )
                retry_count += retries
            except ProviderError as error:
                if error.code != "MODEL_CONTENT_FILTER":
                    raise
                failed_chunks += 1
                rejections.update([error.code])
                continue
            successful_chunks += 1
            extracted = rule_based_extract(chunk, extracted)
            normalized = normalize_chunk_result(project_id, chunk, extracted)
            entities.update((item.id, item) for item in normalized.entities)
            evidence.update((item.id, item) for item in normalized.evidence)
            for item in normalized.facts:
                existing = facts.get(item.id)
                if existing:
                    facts[item.id] = existing.model_copy(
                        update={"evidence_ids": sorted(set(existing.evidence_ids + item.evidence_ids))}
                    )
                else:
                    facts[item.id] = item
            for item in normalized.attributes:
                existing = attributes.get(item.id)
                if existing:
                    attributes[item.id] = existing.model_copy(
                        update={
                            "evidence_ids": sorted(
                                set(existing.evidence_ids + item.evidence_ids)
                            )
                        }
                    )
                else:
                    attributes[item.id] = item
            rejections.update(item.code for item in normalized.rejections)

        document = GraphDocument(
            project=ProjectRecord(id=project_id, title=title),
            chapters=[
                ChapterRecord(
                    id=f"{project_id}:chapter:{chapter.number}",
                    number=chapter.number,
                    title=chapter.title,
                )
                for chapter in split.chapters
            ],
            entities=list(entities.values()),
            facts=list(facts.values()),
            evidence=list(evidence.values()),
            attributes=list(attributes.values()),
        )
        summary = self.importer.import_document(document)
        return PipelineResult(
            quality=QualityReport(
                total_chunks=len(split.chunks),
                successful_chunks=successful_chunks,
                failed_chunks=failed_chunks,
                accepted_entities=len(entities),
                accepted_facts=len(facts),
                accepted_evidence=len(evidence),
                accepted_attributes=len(attributes),
                accepted_attribute_evidence=len(
                    {
                        evidence_id
                        for attribute in attributes.values()
                        for evidence_id in attribute.evidence_ids
                    }
                ),
                rejected_by_code=dict(rejections),
                model_calls=len(split.chunks),
                retry_count=retry_count,
            ),
            import_summary=summary,
        )
