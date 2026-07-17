import json

import httpx
from pydantic import ValidationError

from app.extraction.azure_responses_client import AzureResponsesClient
from app.extraction.models import (
    ExtractionRequest,
    ExtractionResult,
    strict_extraction_schema,
)
from app.extraction.prompting import extraction_system_prompt
from app.extraction.providers import ProviderError, ProviderErrorKind


class AzureOpenAIResponsesProvider:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        timeout_seconds: float = 60,
        client: httpx.Client | None = None,
    ) -> None:
        self.responses = AzureResponsesClient(
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            client=client,
        )

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        content = self.responses.generate_structured(
            messages=[
                {"role": "system", "content": extraction_system_prompt(request)},
                {
                    "role": "user",
                    "content": json.dumps(request.model_dump(), ensure_ascii=False),
                },
            ],
            format_name="knowledge_graph_extraction",
            schema=strict_extraction_schema(),
        )
        try:
            return ExtractionResult.model_validate_json(content)
        except (TypeError, ValueError, ValidationError) as error:
            raise ProviderError(
                ProviderErrorKind.INVALID_RESPONSE, "MODEL_RESPONSE_INVALID"
            ) from error
