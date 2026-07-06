import json

import httpx
from pydantic import ValidationError

from app.extraction.models import ExtractionRequest, ExtractionResult
from app.extraction.providers import ProviderError, ProviderErrorKind


class OpenAICompatibleProvider:
    # Chat Completions structured output contract:
    # https://platform.openai.com/docs/api-reference/chat/create
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        timeout_seconds: float = 60,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=timeout_seconds)

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        try:
            response = self.client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": "Extract only facts supported by the supplied text and return JSON."},
                        {"role": "user", "content": json.dumps(request.model_dump(), ensure_ascii=False)},
                    ],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "knowledge_graph_extraction",
                            "strict": True,
                            "schema": ExtractionResult.model_json_schema(),
                        },
                    },
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            result = ExtractionResult.model_validate_json(content)
            result.validate_for_chunk(request.text)
            return result
        except httpx.HTTPStatusError as error:
            kind = ProviderErrorKind.RETRYABLE if error.response.status_code == 429 or error.response.status_code >= 500 else ProviderErrorKind.CONFIGURATION
            raise ProviderError(kind, f"MODEL_HTTP_{error.response.status_code}") from error
        except httpx.HTTPError as error:
            raise ProviderError(ProviderErrorKind.RETRYABLE, "MODEL_NETWORK_ERROR") from error
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise ProviderError(ProviderErrorKind.INVALID_RESPONSE, "MODEL_RESPONSE_INVALID") from error
