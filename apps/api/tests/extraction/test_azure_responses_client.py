import json

import httpx
import pytest

from app.extraction.azure_responses_client import AzureResponsesClient
from app.extraction.providers import ProviderError, ProviderErrorKind


def completed_response(*texts: str) -> dict:
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": text} for text in texts
                ],
            }
        ],
    }


def client_for(
    transport: httpx.BaseTransport,
    *,
    api_key: str = "secret",
    reasoning_effort: str | None = None,
    max_output_tokens: int | None = None,
):
    return AzureResponsesClient(
        base_url="https://resource.services.ai.azure.com/openai/v1/",
        model="gpt-5.6-sol",
        api_key=api_key,
        reasoning_effort=reasoning_effort,
        max_output_tokens=max_output_tokens,
        client=httpx.Client(transport=transport),
    )


def test_posts_native_responses_structured_output_contract():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=completed_response('{"ok":true}'))

    client = client_for(httpx.MockTransport(handler))
    result = client.generate_structured(
        messages=[
            {"role": "system", "content": "Return JSON."},
            {"role": "user", "content": "Question"},
        ],
        format_name="test_output",
        schema={
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
            "additionalProperties": False,
        },
    )

    sent = captured["request"]
    body = json.loads(sent.content)
    assert sent.url.path == "/openai/v1/responses"
    assert sent.headers["authorization"] == "Bearer secret"
    assert "api-key" not in sent.headers
    assert body["model"] == "gpt-5.6-sol"
    assert body["store"] is False
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["name"] == "test_output"
    assert body["text"]["format"]["strict"] is True
    assert body["text"]["format"]["schema"]["required"] == ["ok"]
    assert "temperature" not in body
    assert "response_format" not in body
    assert "api-version" not in sent.url.params
    assert result == '{"ok":true}'


def test_posts_configured_reasoning_effort_and_output_limit():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=completed_response('{"ok":true}'))

    client = client_for(
        httpx.MockTransport(handler),
        reasoning_effort="low",
        max_output_tokens=12000,
    )

    client.generate_structured(
        messages=[{"role": "user", "content": "Question"}],
        format_name="test_output",
        schema={"type": "object"},
    )

    assert captured["body"]["reasoning"] == {"effort": "low"}
    assert captured["body"]["max_output_tokens"] == 12000


def test_logs_success_latency_request_id_and_usage(caplog):
    payload = completed_response('{"ok":true}')
    payload.update(
        {
            "id": "resp-123",
            "usage": {
                "input_tokens": 100,
                "output_tokens": 20,
                "output_tokens_details": {"reasoning_tokens": 8},
            },
        }
    )
    client = client_for(
        httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )

    with caplog.at_level("INFO"):
        client.generate_structured(
            messages=[{"role": "user", "content": "private novel text"}],
            format_name="test_output",
            schema={"type": "object"},
        )

    assert "Azure Responses request completed" in caplog.text
    assert "format=test_output" in caplog.text
    assert "request_id=resp-123" in caplog.text
    assert "input_tokens=100" in caplog.text
    assert "output_tokens=20" in caplog.text
    assert "reasoning_tokens=8" in caplog.text
    assert "private novel text" not in caplog.text


def test_logs_network_errors_with_duration_and_without_key(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("request timed out", request=request)

    client = client_for(
        httpx.MockTransport(handler), api_key="super-secret-key"
    )

    with caplog.at_level("WARNING"), pytest.raises(
        ProviderError, match="MODEL_NETWORK_ERROR"
    ):
        client.generate_structured(
            messages=[{"role": "user", "content": "Question"}],
            format_name="test_output",
            schema={"type": "object"},
        )

    assert "Azure Responses network error" in caplog.text
    assert "error_type=ReadTimeout" in caplog.text
    assert "duration_seconds=" in caplog.text
    assert "super-secret-key" not in caplog.text


def test_concatenates_ordered_output_text_and_ignores_other_output():
    payload = {
        "status": "completed",
        "output": [
            {"type": "reasoning", "summary": []},
            {
                "type": "message",
                "content": [
                    {"type": "output_text", "text": '{"value":'},
                    {"type": "output_text", "text": "1}"},
                ],
            },
        ],
    }
    client = client_for(
        httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )

    result = client.generate_structured(
        messages=[{"role": "user", "content": "Question"}],
        format_name="value",
        schema={"type": "object"},
    )

    assert result == '{"value":1}'


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"status": "incomplete", "output": []}, "MODEL_RESPONSE_INCOMPLETE"),
        ({}, "MODEL_RESPONSE_INVALID"),
        (
            {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "refusal", "refusal": "blocked"}],
                    }
                ],
            },
            "MODEL_RESPONSE_REFUSED",
        ),
        ({"status": "completed", "output": []}, "MODEL_RESPONSE_INVALID"),
    ],
)
def test_rejects_non_completed_refused_and_empty_responses(payload, code):
    client = client_for(
        httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    )

    with pytest.raises(ProviderError, match=code):
        client.generate_structured(
            messages=[{"role": "user", "content": "Question"}],
            format_name="value",
            schema={"type": "object"},
        )


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (401, ProviderErrorKind.CONFIGURATION),
        (403, ProviderErrorKind.CONFIGURATION),
        (404, ProviderErrorKind.CONFIGURATION),
        (408, ProviderErrorKind.RETRYABLE),
        (409, ProviderErrorKind.RETRYABLE),
        (429, ProviderErrorKind.RETRYABLE),
        (503, ProviderErrorKind.RETRYABLE),
    ],
)
def test_maps_http_statuses(status, kind):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status,
            json={"error": {"code": "failure"}},
            headers={"retry-after-ms": "1250"},
        )

    client = client_for(httpx.MockTransport(handler))

    with pytest.raises(ProviderError) as caught:
        client.generate_structured(
            messages=[{"role": "user", "content": "Question"}],
            format_name="value",
            schema={"type": "object"},
        )

    assert caught.value.kind == kind
    assert caught.value.code == f"MODEL_HTTP_{status}"
    assert caught.value.retry_after_seconds == 1.25


def test_maps_content_filter_and_does_not_log_key(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={
                "error": {
                    "code": "content_filter",
                    "innererror": {"code": "ResponsibleAIPolicyViolation"},
                }
            },
        )

    client = client_for(
        httpx.MockTransport(handler), api_key="super-secret-key"
    )

    with pytest.raises(ProviderError, match="MODEL_CONTENT_FILTER"):
        client.generate_structured(
            messages=[{"role": "user", "content": "Question"}],
            format_name="value",
            schema={"type": "object"},
        )

    assert "Azure Responses HTTP error status=400" in caplog.text
    assert "super-secret-key" not in caplog.text
