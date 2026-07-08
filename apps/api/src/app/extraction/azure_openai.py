import json
import logging

import httpx
from pydantic import ValidationError

from app.extraction.models import (
    ExtractionRequest,
    ExtractionResult,
    strict_extraction_schema,
)
from app.extraction.providers import ProviderError, ProviderErrorKind


logger = logging.getLogger(__name__)


def _response_excerpt(response: httpx.Response, limit: int = 1000) -> str:
    text = response.text.replace("\n", "\\n")
    return text[:limit]


class AzureOpenAIProvider:
    # Azure OpenAI chat completions use deployment-scoped URLs and `api-key` auth:
    # https://learn.microsoft.com/azure/ai-services/openai/reference
    def __init__(
        self,
        *,
        base_url: str,
        deployment: str,
        api_version: str,
        api_key: str,
        timeout_seconds: float = 60,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.deployment = deployment
        self.api_version = api_version
        self.api_key = api_key
        self.client = client or httpx.Client(timeout=timeout_seconds)

    def extract(self, request: ExtractionRequest) -> ExtractionResult:
        try:
            response = self.client.post(
                f"{self.base_url}/openai/deployments/{self.deployment}/chat/completions",
                params={"api-version": self.api_version},
                headers={"api-key": self.api_key},
                json={
                    "messages": [
                        {
                            "role": "system",
                            "content": "Extract only facts supported by the supplied text and return JSON.",
                        },
                        {
                            "role": "user",
                            "content": json.dumps(
                                request.model_dump(), ensure_ascii=False
                            ),
                        },
                    ],
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "knowledge_graph_extraction",
                            "strict": True,
                            "schema": strict_extraction_schema(),
                        },
                    },
                },
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            result = ExtractionResult.model_validate_json(content)
            return result
        except httpx.HTTPStatusError as error:
            kind = (
                ProviderErrorKind.RETRYABLE
                if error.response.status_code == 429
                or error.response.status_code >= 500
                else ProviderErrorKind.CONFIGURATION
            )
            logger.warning(
                "Azure OpenAI HTTP error status=%s deployment=%s response=%s",
                error.response.status_code,
                self.deployment,
                _response_excerpt(error.response),
            )
            raise ProviderError(kind, f"MODEL_HTTP_{error.response.status_code}") from error
        except httpx.HTTPError as error:
            raise ProviderError(ProviderErrorKind.RETRYABLE, "MODEL_NETWORK_ERROR") from error
        except (KeyError, TypeError, ValueError, ValidationError) as error:
            raise ProviderError(
                ProviderErrorKind.INVALID_RESPONSE, "MODEL_RESPONSE_INVALID"
            ) from error
