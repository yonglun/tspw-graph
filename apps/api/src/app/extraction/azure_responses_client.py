from __future__ import annotations

import logging
import time
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
        reasoning_effort: str | None = None,
        max_output_tokens: int | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.reasoning_effort = reasoning_effort
        self.max_output_tokens = max_output_tokens
        self.client = client or httpx.Client(timeout=timeout_seconds)

    def generate_structured(
        self,
        *,
        messages: list[dict[str, str]],
        format_name: str,
        schema: dict[str, Any],
    ) -> str:
        started_at = time.perf_counter()
        try:
            body: dict[str, Any] = {
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
            }
            if self.reasoning_effort is not None:
                body["reasoning"] = {"effort": self.reasoning_effort}
            if self.max_output_tokens is not None:
                body["max_output_tokens"] = self.max_output_tokens
            response = self.client.post(
                f"{self.base_url}/responses",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=body,
            )
            response.raise_for_status()
            payload = response.json()
            self._log_success(
                response,
                payload,
                format_name=format_name,
                duration_seconds=time.perf_counter() - started_at,
            )
            return self._output_text(payload)
        except ProviderError:
            raise
        except httpx.HTTPStatusError as error:
            self._raise_http_error(
                error,
                format_name=format_name,
                duration_seconds=time.perf_counter() - started_at,
            )
        except httpx.HTTPError as error:
            logger.warning(
                "Azure Responses network error model=%s format=%s "
                "duration_seconds=%.2f error_type=%s",
                self.model,
                format_name,
                time.perf_counter() - started_at,
                type(error).__name__,
            )
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

    @staticmethod
    def _request_id(
        response: httpx.Response, payload: dict[str, Any] | None = None
    ) -> str:
        return (
            response.headers.get("x-request-id")
            or response.headers.get("apim-request-id")
            or str((payload or {}).get("id") or "unknown")
        )

    def _log_success(
        self,
        response: httpx.Response,
        payload: dict[str, Any],
        *,
        format_name: str,
        duration_seconds: float,
    ) -> None:
        usage = payload.get("usage") or {}
        output_details = usage.get("output_tokens_details") or {}
        logger.info(
            "Azure Responses request completed model=%s format=%s "
            "duration_seconds=%.2f status=%s request_id=%s "
            "input_tokens=%s output_tokens=%s reasoning_tokens=%s "
            "total_tokens=%s",
            self.model,
            format_name,
            duration_seconds,
            payload.get("status", "unknown"),
            self._request_id(response, payload),
            usage.get("input_tokens", "unknown"),
            usage.get("output_tokens", "unknown"),
            output_details.get("reasoning_tokens", "unknown"),
            usage.get("total_tokens", "unknown"),
        )

    def _raise_http_error(
        self,
        error: httpx.HTTPStatusError,
        *,
        format_name: str,
        duration_seconds: float,
    ) -> None:
        response = error.response
        logger.warning(
            "Azure Responses HTTP error status=%s model=%s format=%s "
            "duration_seconds=%.2f request_id=%s response=%s",
            response.status_code,
            self.model,
            format_name,
            duration_seconds,
            self._request_id(response),
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
