import json

import httpx
import pytest

from app.extraction.models import ExtractionRequest
from app.extraction.azure_openai import AzureOpenAIProvider
from app.extraction.ollama import OllamaProvider
from app.extraction.openai_compatible import OpenAICompatibleProvider
from app.extraction.providers import ProviderError


FIXED = json.dumps(
    {
        "entities": [
            {"local_id": "p1", "name": "令狐冲", "type": "Person", "aliases": []}
        ],
        "facts": [],
    },
    ensure_ascii=False,
)


def request() -> ExtractionRequest:
    return ExtractionRequest(
        project_id="p-1", chunk_id="c-1", text="令狐冲", ontology={"types": ["Person"]}
    )


def assert_strict_schema(schema):
    if schema.get("type") == "object":
        properties = schema["properties"]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(properties)
        assert "default" not in schema
        for child in properties.values():
            assert_strict_schema(child)
    if schema.get("type") == "array":
        assert_strict_schema(schema["items"])


def test_openai_provider_uses_json_schema_and_bearer_auth():
    captured = {}

    def handler(http_request: httpx.Request) -> httpx.Response:
        captured["request"] = http_request
        return httpx.Response(200, json={"choices": [{"message": {"content": FIXED}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = OpenAICompatibleProvider(
        base_url="http://fake/v1", model="demo", api_key="secret", client=client
    ).extract(request())

    sent = captured["request"]
    body = json.loads(sent.content)
    assert sent.url.path == "/v1/chat/completions"
    assert sent.headers["authorization"] == "Bearer secret"
    assert body["response_format"]["type"] == "json_schema"
    assert_strict_schema(body["response_format"]["json_schema"]["schema"])
    assert result.entities[0].name == "令狐冲"


def test_azure_openai_provider_uses_deployment_api_version_and_api_key_header():
    captured = {}

    def handler(http_request: httpx.Request) -> httpx.Response:
        captured["request"] = http_request
        return httpx.Response(200, json={"choices": [{"message": {"content": FIXED}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = AzureOpenAIProvider(
        base_url="https://example.openai.azure.com",
        deployment="kg-extractor",
        api_version="2024-06-01",
        api_key="azure-secret",
        client=client,
    ).extract(request())

    sent = captured["request"]
    body = json.loads(sent.content)
    assert sent.url.path == "/openai/deployments/kg-extractor/chat/completions"
    assert sent.url.params["api-version"] == "2024-06-01"
    assert sent.headers["api-key"] == "azure-secret"
    assert "authorization" not in sent.headers
    assert body["response_format"]["type"] == "json_schema"
    assert_strict_schema(body["response_format"]["json_schema"]["schema"])
    assert result.entities[0].name == "令狐冲"


def test_azure_openai_provider_logs_http_error_response_without_key(caplog):
    def handler(http_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": {"code": "content_filter", "message": "blocked"}},
            request=http_request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = AzureOpenAIProvider(
        base_url="https://example.openai.azure.com",
        deployment="kg-extractor",
        api_version="2025-01-01-preview",
        api_key="azure-secret",
        client=client,
    )

    with pytest.raises(ProviderError, match="MODEL_HTTP_400"):
        provider.extract(request())

    assert "Azure OpenAI HTTP error status=400" in caplog.text
    assert "content_filter" in caplog.text
    assert "azure-secret" not in caplog.text


def test_ollama_provider_uses_non_streaming_schema_format():
    captured = {}

    def handler(http_request: httpx.Request) -> httpx.Response:
        captured["request"] = http_request
        return httpx.Response(200, json={"message": {"content": FIXED}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = OllamaProvider(
        base_url="http://fake", model="qwen3", client=client
    ).extract(request())

    sent = captured["request"]
    body = json.loads(sent.content)
    assert sent.url.path == "/api/chat"
    assert body["stream"] is False
    assert body["format"]["type"] == "object"
    assert result.entities[0].name == "令狐冲"
