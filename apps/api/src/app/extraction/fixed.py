from app.extraction.models import ExtractionRequest, ExtractionResult


class FixedProvider:
    def __init__(self, result: ExtractionResult | None = None) -> None:
        self.result = result or ExtractionResult()

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        self.result.validate_for_chunk(request.text)
        return self.result.model_copy(deep=True)
