import json

import httpx
from pydantic import ValidationError

from app.extraction.models import ExtractionRequest, ExtractionResult
from app.extraction.prompting import extraction_system_prompt
from app.extraction.providers import (
    ProviderError,
    ProviderErrorKind,
    parse_retry_after_seconds,
)


class OllamaProvider:
    # Ollama documents JSON Schema in `format` with `stream: false`:
    # https://docs.ollama.com/capabilities/structured-outputs
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float = 60,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = client or httpx.Client(timeout=timeout_seconds)

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        try:
            response = self.client.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": extraction_system_prompt(request),
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                request.model_dump(), ensure_ascii=False
                            ),
                        },
                    ],
                    "stream": False,
                    "format": ExtractionResult.model_json_schema(),
                    "options": {"temperature": 0},
                },
            )
            response.raise_for_status()
            content = response.json()["message"]["content"]
            result = ExtractionResult.model_validate_json(content)
            return result
        except httpx.HTTPStatusError as error:
            kind = (
                ProviderErrorKind.RETRYABLE
                if error.response.status_code == 429
                or error.response.status_code >= 500
                else ProviderErrorKind.CONFIGURATION
            )
            raise ProviderError(
                kind,
                f"MODEL_HTTP_{error.response.status_code}",
                retry_after_seconds=parse_retry_after_seconds(error.response.headers),
            ) from error
        except httpx.HTTPError as error:
            raise ProviderError(ProviderErrorKind.RETRYABLE, "MODEL_NETWORK_ERROR") from error
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise ProviderError(
                ProviderErrorKind.INVALID_RESPONSE, "MODEL_RESPONSE_INVALID"
            ) from error
