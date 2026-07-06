import json

import httpx

from app.extraction.models import ExtractionRequest
from app.extraction.ollama import OllamaProvider
from app.extraction.openai_compatible import OpenAICompatibleProvider


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
    assert result.entities[0].name == "令狐冲"


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
