import json

import httpx
import pytest

import app.qa.llm as qa_llm
from app.ontology.catalog import CATALOG
from app.qa.intents import QaIntent
from app.qa.llm import QaIntentProvider
from app.extraction.providers import ProviderError


class FakeClient:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code
        self.requests = []

    def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return httpx.Response(
            self.status_code,
            json=self.payload,
            request=httpx.Request("POST", url),
        )


def provider(client):
    return QaIntentProvider(
        base_url="https://example.openai.azure.com",
        deployment="gpt-4o",
        api_version="2024-12-01-preview",
        api_key="secret",
        client=client,
    )


def responses_provider(client):
    return qa_llm.QaResponsesIntentProvider(
        base_url="https://resource.services.ai.azure.com/openai/v1",
        model="gpt-5.6-sol",
        api_key="secret",
        client=client,
    )


def responses_payload(content: str) -> dict:
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": content}],
            }
        ],
    }


def test_parses_strict_intent_and_sends_allowlist():
    client = FakeClient({
        "choices": [{"message": {"content": json.dumps({
            "intent": "RELATION",
            "subject": "令狐冲",
            "relation": "MEMBER_OF",
            "property": None,
            "confidence": 0.96,
        }, ensure_ascii=False)}}]
    })

    intent = provider(client).parse("他属于哪个门派？", CATALOG)

    assert isinstance(intent, QaIntent)
    assert intent.relation == "MEMBER_OF"
    url, request = client.requests[0]
    assert "/openai/deployments/gpt-4o/chat/completions" in url
    assert request["headers"]["api-key"] == "secret"
    assert request["json"]["response_format"]["type"] == "json_schema"
    assert "MEMBER_OF" in request["json"]["messages"][0]["content"]


def test_rejects_unknown_relation_and_low_confidence():
    unknown = FakeClient({
        "choices": [{"message": {"content": json.dumps({
            "intent": "RELATION", "subject": "令狐冲", "relation": "DELETE_ALL",
            "property": None, "confidence": 0.99,
        })}}]
    })
    low = FakeClient({
        "choices": [{"message": {"content": json.dumps({
            "intent": "ATTRIBUTE", "subject": "令狐冲", "relation": None,
            "property": "gender", "confidence": 0.2,
        })}}]
    })

    with pytest.raises(ProviderError, match="QA_INTENT_INVALID"):
        provider(unknown).parse("问题", CATALOG)
    with pytest.raises(ProviderError, match="QA_INTENT_LOW_CONFIDENCE"):
        provider(low).parse("问题", CATALOG)


def test_maps_http_and_json_failures_to_provider_errors():
    unavailable = FakeClient({"error": {"code": "rate_limit_exceeded"}}, status_code=429)
    malformed = FakeClient({"choices": [{"message": {"content": "not-json"}}]})

    with pytest.raises(ProviderError) as error:
        provider(unavailable).parse("问题", CATALOG)
    assert error.value.kind.value == "RETRYABLE"
    with pytest.raises(ProviderError, match="MODEL_RESPONSE_INVALID"):
        provider(malformed).parse("问题", CATALOG)


def test_responses_provider_parses_intent_and_uses_native_schema():
    content = json.dumps(
        {
            "intent": "ATTRIBUTE",
            "subject": "令狐冲",
            "relation": None,
            "property": "gender",
            "confidence": 0.95,
        },
        ensure_ascii=False,
    )
    client = FakeClient(responses_payload(content))

    intent = responses_provider(client).parse("令狐冲的性别是什么？", CATALOG)

    assert intent.property == "gender"
    url, request = client.requests[0]
    assert url.endswith("/openai/v1/responses")
    assert request["headers"]["Authorization"] == "Bearer secret"
    assert request["json"]["text"]["format"]["name"] == "qa_intent"
    assert "gender" in request["json"]["input"][0]["content"]


def test_responses_provider_preserves_low_confidence_validation():
    content = json.dumps(
        {
            "intent": "ATTRIBUTE",
            "subject": "令狐冲",
            "relation": None,
            "property": "gender",
            "confidence": 0.2,
        },
        ensure_ascii=False,
    )
    client = FakeClient(responses_payload(content))

    with pytest.raises(ProviderError, match="QA_INTENT_LOW_CONFIDENCE"):
        responses_provider(client).parse("令狐冲的性别是什么？", CATALOG)
