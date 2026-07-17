from __future__ import annotations

import logging
from typing import Any

import httpx

from app.extraction.providers import (
    ProviderError,
    ProviderErrorKind,
    parse_retry_after_seconds,
)


logger = logging.getLogger(__name__)


def _response_excerpt(response: httpx.Response, limit: int = 1000) -> str:
    return response.text.replace("\n", "\\n")[:limit]


def _is_content_filter_response(response: httpx.Response) -> bool:
    try:
        error = response.json().get("error", {})
    except (AttributeError, ValueError):
        return False
    inner = error.get("innererror") or {}
    return (
        error.get("code") == "content_filter"
        or inner.get("code") == "ResponsibleAIPolicyViolation"
    )


class AzureResponsesClient:
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

    def generate_structured(
        self,
        *,
        messages: list[dict[str, str]],
        format_name: str,
        schema: dict[str, Any],
    ) -> str:
        try:
            response = self.client.post(
                f"{self.base_url}/responses",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "input": messages,
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": format_name,
                            "strict": True,
                            "schema": schema,
                        }
                    },
                    "store": False,
                },
            )
            response.raise_for_status()
            return self._output_text(response.json())
        except ProviderError:
            raise
        except httpx.HTTPStatusError as error:
            self._raise_http_error(error)
        except httpx.HTTPError as error:
            raise ProviderError(
                ProviderErrorKind.RETRYABLE, "MODEL_NETWORK_ERROR"
            ) from error
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise ProviderError(
                ProviderErrorKind.INVALID_RESPONSE, "MODEL_RESPONSE_INVALID"
            ) from error

    @staticmethod
    def _output_text(payload: dict[str, Any]) -> str:
        status = payload.get("status")
        if status is None:
            raise ProviderError(
                ProviderErrorKind.INVALID_RESPONSE, "MODEL_RESPONSE_INVALID"
            )
        if status != "completed":
            raise ProviderError(
                ProviderErrorKind.INVALID_RESPONSE, "MODEL_RESPONSE_INCOMPLETE"
            )

        parts: list[str] = []
        for item in payload.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "refusal":
                    raise ProviderError(
                        ProviderErrorKind.INVALID_RESPONSE,
                        "MODEL_RESPONSE_REFUSED",
                    )
                if content.get("type") == "output_text":
                    parts.append(content["text"])
        if not parts:
            raise ProviderError(
                ProviderErrorKind.INVALID_RESPONSE, "MODEL_RESPONSE_INVALID"
            )
        return "".join(parts)

    def _raise_http_error(self, error: httpx.HTTPStatusError) -> None:
        response = error.response
        logger.warning(
            "Azure Responses HTTP error status=%s model=%s response=%s",
            response.status_code,
            self.model,
            _response_excerpt(response),
        )
        if _is_content_filter_response(response):
            raise ProviderError(
                ProviderErrorKind.INVALID_RESPONSE, "MODEL_CONTENT_FILTER"
            ) from error

        status = response.status_code
        kind = (
            ProviderErrorKind.RETRYABLE
            if status in {408, 409, 429} or status >= 500
            else ProviderErrorKind.CONFIGURATION
        )
        raise ProviderError(
            kind,
            f"MODEL_HTTP_{status}",
            retry_after_seconds=parse_retry_after_seconds(response.headers),
        ) from error
