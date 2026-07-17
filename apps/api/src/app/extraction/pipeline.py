from collections import Counter
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
import logging
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
from app.extraction.splitter import TextChunk, split_document
from app.graph.importer import GraphImporter
from app.graph.models import (
    AttributeAssertionRecord, ChapterRecord, EntityRecord, EvidenceRecord,
    FactRecord, GraphDocument, ImportSummary, ProjectRecord,
)
from app.ontology.catalog import CATALOG


logger = logging.getLogger(__name__)


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


class PipelineCancelled(RuntimeError):
    """Raised when a build is cancelled at a safe chunk boundary."""


@dataclass(frozen=True)
class ChunkExtractionOutcome:
    index: int
    chunk: TextChunk
    extracted: ExtractionResult | None
    retries: int = 0
    error_code: str | None = None


class ExtractionPipeline:
    def __init__(
        self,
        importer: GraphImporter,
        *,
        max_retries: int = 3,
        retry_backoff_seconds: float = 5.0,
        retry_sleep: Callable[[float], None] = time.sleep,
        concurrency: int = 1,
    ) -> None:
        if not 1 <= concurrency <= 16:
            raise ValueError("concurrency must be between 1 and 16")
        self.importer = importer
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds
        self.retry_sleep = retry_sleep
        self.concurrency = concurrency

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
                if error.kind != ProviderErrorKind.RETRYABLE:
                    raise
                if retries >= self.max_retries:
                    logger.warning(
                        "Extraction request retry exhausted chunk_id=%s "
                        "code=%s retries=%s",
                        request.chunk_id,
                        error.code,
                        retries,
                    )
                    raise
                retries += 1
                delay = self._retry_delay(error, retries)
                logger.warning(
                    "Extraction request retry scheduled chunk_id=%s "
                    "code=%s retry=%s/%s delay_seconds=%.2f",
                    request.chunk_id,
                    error.code,
                    retries,
                    self.max_retries,
                    delay,
                )
                self.retry_sleep(delay)

    def _extract_chunk(
        self,
        index: int,
        chunk: TextChunk,
        provider: ExtractionProvider,
        request: ExtractionRequest,
    ) -> ChunkExtractionOutcome:
        try:
            extracted, retries = self._extract_with_retries(provider, request)
        except ProviderError as error:
            if error.code != "MODEL_CONTENT_FILTER":
                raise
            return ChunkExtractionOutcome(
                index=index,
                chunk=chunk,
                extracted=None,
                error_code=error.code,
            )
        return ChunkExtractionOutcome(
            index=index,
            chunk=chunk,
            extracted=extracted,
            retries=retries,
        )

    def _extract_chunks(
        self,
        project_id: str,
        chunks: list[TextChunk],
        provider: ExtractionProvider,
        ontology: dict,
        report_progress: Callable[[int, int], None],
        is_cancelled: Callable[[], bool],
    ) -> list[ChunkExtractionOutcome]:
        total_chunks = len(chunks)
        if is_cancelled():
            raise PipelineCancelled("JOB_CANCELLED")
        if not chunks:
            return []

        logger.info(
            "Extraction batch started project_id=%s chunks=%s concurrency=%s",
            project_id,
            total_chunks,
            self.concurrency,
        )
        executor = ThreadPoolExecutor(
            max_workers=self.concurrency,
            thread_name_prefix="extraction",
        )
        pending: dict[Future[ChunkExtractionOutcome], tuple[int, TextChunk]] = {}
        outcomes: list[ChunkExtractionOutcome] = []
        next_index = 0
        completed = 0

        def submit_available() -> None:
            nonlocal next_index
            while next_index < total_chunks and len(pending) < self.concurrency:
                if is_cancelled():
                    raise PipelineCancelled("JOB_CANCELLED")
                index = next_index
                chunk = chunks[index]
                request = ExtractionRequest(
                    project_id=project_id,
                    chunk_id=chunk.id,
                    text=chunk.text,
                    ontology=ontology,
                )
                future = executor.submit(
                    self._extract_chunk,
                    index,
                    chunk,
                    provider,
                    request,
                )
                pending[future] = (index, chunk)
                next_index += 1

        try:
            submit_available()
            while pending:
                completed_futures, _ = wait(
                    pending,
                    return_when=FIRST_COMPLETED,
                )
                for future in completed_futures:
                    index, chunk = pending.pop(future)
                    try:
                        outcome = future.result()
                    except ProviderError as error:
                        logger.error(
                            "Extraction batch failed project_id=%s "
                            "chunk_id=%s code=%s",
                            project_id,
                            chunk.id,
                            error.code,
                            exc_info=True,
                        )
                        raise
                    except Exception:
                        logger.exception(
                            "Extraction batch failed project_id=%s chunk_id=%s",
                            project_id,
                            chunk.id,
                        )
                        raise
                    outcomes.append(outcome)
                    completed += 1
                    report_progress(completed, total_chunks)
                if is_cancelled():
                    raise PipelineCancelled("JOB_CANCELLED")
                submit_available()
        except PipelineCancelled:
            logger.info(
                "Extraction batch cancelled project_id=%s completed=%s total=%s",
                project_id,
                completed,
                total_chunks,
            )
            for future in pending:
                future.cancel()
            raise
        except Exception:
            for future in pending:
                future.cancel()
            raise
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

        return sorted(outcomes, key=lambda outcome: outcome.index)

    def process(
        self,
        project_id: str,
        title: str,
        source: str,
        provider: ExtractionProvider,
        *,
        attributes_only: bool = False,
        on_progress: Callable[[int, int], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> PipelineResult:
        split = split_document(source)
        total_chunks = len(split.chunks)
        report_progress = on_progress or (lambda _completed, _total: None)
        is_cancelled = should_cancel or (lambda: False)
        report_progress(0, total_chunks)
        entities: dict[str, EntityRecord] = {}
        evidence: dict[str, EvidenceRecord] = {}
        facts: dict[str, FactRecord] = {}
        attributes: dict[str, AttributeAssertionRecord] = {}
        rejections: Counter[str] = Counter()
        failed_chunks = 0
        successful_chunks = 0
        retry_count = 0
        ontology = {
            "entity_types": [item.id.value for item in CATALOG.entity_types],
            "relation_types": [item.id.value for item in CATALOG.relation_types],
            "property_definitions": {
                item.id.value: [
                    definition.model_dump(mode="json")
                    for definition in item.effective_property_definitions
                ]
                for item in CATALOG.entity_types
            },
        }
        outcomes = self._extract_chunks(
            project_id,
            list(split.chunks),
            provider,
            ontology,
            report_progress,
            is_cancelled,
        )
        for outcome in outcomes:
            chunk = outcome.chunk
            retry_count += outcome.retries
            if outcome.error_code:
                failed_chunks += 1
                rejections.update([outcome.error_code])
                continue
            extracted = outcome.extracted
            if extracted is None:
                raise RuntimeError("missing extraction result")
            successful_chunks += 1
            if not attributes_only:
                extracted = rule_based_extract(chunk, extracted)
            normalized = normalize_chunk_result(project_id, chunk, extracted)
            entities.update((item.id, item) for item in normalized.entities)
            if attributes_only:
                attribute_evidence_ids = {
                    evidence_id
                    for attribute in normalized.attributes
                    for evidence_id in attribute.evidence_ids
                }
                evidence.update(
                    (item.id, item)
                    for item in normalized.evidence
                    if item.id in attribute_evidence_ids
                )
            else:
                evidence.update((item.id, item) for item in normalized.evidence)
                for item in normalized.facts:
                    existing = facts.get(item.id)
                    if existing:
                        facts[item.id] = existing.model_copy(
                            update={
                                "evidence_ids": sorted(
                                    set(existing.evidence_ids + item.evidence_ids)
                                )
                            }
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

        if is_cancelled():
            raise PipelineCancelled("JOB_CANCELLED")
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
        summary = (
            self.importer.import_attributes(document)
            if attributes_only
            else self.importer.import_document(document)
        )
        accepted_entities = 0 if attributes_only else len(entities)
        accepted_facts = 0 if attributes_only else len(facts)
        accepted_evidence = summary.retained_evidence
        return PipelineResult(
            quality=QualityReport(
                total_chunks=total_chunks,
                successful_chunks=successful_chunks,
                failed_chunks=failed_chunks,
                accepted_entities=accepted_entities,
                accepted_facts=accepted_facts,
                accepted_evidence=accepted_evidence,
                accepted_attributes=summary.retained_attributes,
                accepted_attribute_evidence=summary.retained_attribute_evidence,
                rejected_by_code=dict(rejections),
                model_calls=total_chunks,
                retry_count=retry_count,
            ),
            import_summary=summary,
        )
