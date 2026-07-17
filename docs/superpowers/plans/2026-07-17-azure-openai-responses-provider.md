# Azure OpenAI Responses Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Azure OpenAI v1 Responses API support for both structured knowledge-graph extraction and structured QA intent parsing while preserving every existing provider.

**Architecture:** Add a shared HTTPX-based `AzureResponsesClient` for the Azure v1 transport and output envelope. Build one extraction adapter and one QA adapter on top of that client, then extend the existing provider registry with the explicit `azure-openai-responses` profile kind.

**Tech Stack:** Python 3.12+, HTTPX 0.28, Pydantic 2, pytest 8, FastAPI settings, Docker Compose.

## Global Constraints

- Keep `azure-openai`, `openai-compatible`, `ollama`, and `fixed` behavior unchanged.
- Use API-key authentication only: `Authorization: Bearer <key>`.
- Configure the endpoint at `/openai/v1`; the client appends `/responses`.
- Use Responses structured output through `text.format`, with `strict: true`.
- Always send `store: false`.
- Do not send `temperature`, legacy `response_format`, or `api-version`.
- Do not add the OpenAI Python SDK; reuse the installed `httpx>=0.28,<1` dependency.
- Do not log API keys, Authorization headers, or complete source chunks.
- Do not change the frontend, database schema, chunking, graph import, or task state machine.

---

## File Structure

- Create `apps/api/src/app/extraction/azure_responses_client.py`: protocol-only Azure v1 Responses transport, output parsing, and error mapping.
- Create `apps/api/src/app/extraction/azure_responses.py`: graph extraction adapter implementing `ExtractionProvider`.
- Modify `apps/api/src/app/extraction/providers.py`: register the new extraction and QA implementations.
- Modify `apps/api/src/app/qa/llm.py`: share QA intent validation and add the Responses-based QA adapter.
- Create `apps/api/tests/extraction/test_azure_responses_client.py`: focused transport, parsing, error, and secret-safety tests.
- Modify `apps/api/tests/extraction/test_provider_contracts.py`: extraction request contract test.
- Modify `apps/api/tests/extraction/test_providers.py`: registry construction coverage.
- Modify `apps/api/tests/qa/test_llm.py`: Responses QA request, parsing, and validation coverage.
- Modify `.env.example`: add a runnable profile template and QA selector.
- Modify `compose.yaml`: pass `QA_MODEL_PROFILE_ID` into application containers.
- Modify `docs/deployment-docker-azure-openai.md`: document deployment, verification, and smoke testing.

---

### Task 1: Shared Azure Responses transport

**Files:**
- Create: `apps/api/src/app/extraction/azure_responses_client.py`
- Create: `apps/api/tests/extraction/test_azure_responses_client.py`

**Interfaces:**
- Consumes: `ProviderError`, `ProviderErrorKind`, and `parse_retry_after_seconds` from `app.extraction.providers`.
- Produces: `AzureResponsesClient.generate_structured(*, messages: list[dict[str, str]], format_name: str, schema: dict[str, Any]) -> str`.

- [ ] **Step 1: Write failing request and output parsing tests**

Create `apps/api/tests/extraction/test_azure_responses_client.py` with these fixtures and tests:

```python
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


def test_posts_native_responses_structured_output_contract():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=completed_response('{"ok":true}'))

    client = AzureResponsesClient(
        base_url="https://resource.services.ai.azure.com/openai/v1/",
        model="gpt-5.6-sol",
        api_key="secret",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

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
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    client = AzureResponsesClient(
        base_url="https://resource.services.ai.azure.com/openai/v1",
        model="gpt-5.6-sol",
        api_key="secret",
        client=httpx.Client(transport=transport),
    )

    result = client.generate_structured(
        messages=[{"role": "user", "content": "Question"}],
        format_name="value",
        schema={"type": "object"},
    )

    assert result == '{"value":1}'
```

- [ ] **Step 2: Run the tests and verify the missing module failure**

Run:

```bash
cd apps/api
pytest tests/extraction/test_azure_responses_client.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named 'app.extraction.azure_responses_client'`.

- [ ] **Step 3: Implement the minimal shared client**

Create `apps/api/src/app/extraction/azure_responses_client.py`:

```python
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
    except ValueError:
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
                        ProviderErrorKind.INVALID_RESPONSE, "MODEL_RESPONSE_REFUSED"
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
```

- [ ] **Step 4: Run the request and parsing tests**

Run:

```bash
cd apps/api
pytest tests/extraction/test_azure_responses_client.py -v
```

Expected: `2 passed`.

- [ ] **Step 5: Add refusal, incomplete, HTTP, retry, and secret-safety tests**

Append these tests to `apps/api/tests/extraction/test_azure_responses_client.py`:

```python
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
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
    client = AzureResponsesClient(
        base_url="https://resource.services.ai.azure.com/openai/v1",
        model="gpt-5.6-sol",
        api_key="secret",
        client=httpx.Client(transport=transport),
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

    client = AzureResponsesClient(
        base_url="https://resource.services.ai.azure.com/openai/v1",
        model="gpt-5.6-sol",
        api_key="secret",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

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

    client = AzureResponsesClient(
        base_url="https://resource.services.ai.azure.com/openai/v1",
        model="gpt-5.6-sol",
        api_key="super-secret-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(ProviderError, match="MODEL_CONTENT_FILTER"):
        client.generate_structured(
            messages=[{"role": "user", "content": "Question"}],
            format_name="value",
            schema={"type": "object"},
        )

    assert "Azure Responses HTTP error status=400" in caplog.text
    assert "super-secret-key" not in caplog.text
```

- [ ] **Step 6: Run all shared-client tests**

Run:

```bash
cd apps/api
pytest tests/extraction/test_azure_responses_client.py -v
```

Expected: all parameterized cases pass.

- [ ] **Step 7: Commit the shared transport**

```bash
git add apps/api/src/app/extraction/azure_responses_client.py apps/api/tests/extraction/test_azure_responses_client.py
git commit -m "feat: add Azure Responses transport"
```

---

### Task 2: Knowledge-graph extraction adapter

**Files:**
- Create: `apps/api/src/app/extraction/azure_responses.py`
- Modify: `apps/api/src/app/extraction/providers.py`
- Modify: `apps/api/tests/extraction/test_provider_contracts.py`
- Modify: `apps/api/tests/extraction/test_providers.py`

**Interfaces:**
- Consumes: `AzureResponsesClient.generate_structured(...) -> str` from Task 1.
- Produces: `AzureOpenAIResponsesProvider.extract(request: ExtractionRequest) -> ExtractionResult` and registry support for provider kind `azure-openai-responses`.

- [ ] **Step 1: Write the failing extraction contract test**

Add the import to `apps/api/tests/extraction/test_provider_contracts.py`:

```python
from app.extraction.azure_responses import AzureOpenAIResponsesProvider
```

Add this test:

```python
def test_azure_responses_provider_uses_extraction_schema_and_parses_output():
    captured = {}

    def handler(http_request: httpx.Request) -> httpx.Response:
        captured["request"] = http_request
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": FIXED}],
                    }
                ],
            },
        )

    result = AzureOpenAIResponsesProvider(
        base_url="https://resource.services.ai.azure.com/openai/v1",
        model="gpt-5.6-sol",
        api_key="azure-secret",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    ).extract(request())

    sent = captured["request"]
    body = json.loads(sent.content)
    assert body["text"]["format"]["name"] == "knowledge_graph_extraction"
    assert_strict_schema(body["text"]["format"]["schema"])
    assert "令狐冲" in body["input"][1]["content"]
    assert result.entities[0].name == "令狐冲"
```

- [ ] **Step 2: Run the contract test and verify the missing adapter failure**

Run:

```bash
cd apps/api
pytest tests/extraction/test_provider_contracts.py::test_azure_responses_provider_uses_extraction_schema_and_parses_output -v
```

Expected: collection fails because `app.extraction.azure_responses` does not exist.

- [ ] **Step 3: Implement the extraction adapter**

Create `apps/api/src/app/extraction/azure_responses.py`:

```python
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
```

- [ ] **Step 4: Run the extraction contract test**

Run:

```bash
cd apps/api
pytest tests/extraction/test_provider_contracts.py::test_azure_responses_provider_uses_extraction_schema_and_parses_output -v
```

Expected: `1 passed`.

- [ ] **Step 5: Write the failing registry test**

Add this import to `apps/api/tests/extraction/test_providers.py`:

```python
from app.extraction.azure_responses import AzureOpenAIResponsesProvider
```

Inside `test_registry_builds_all_supported_providers`, construct the new profile:

```python
    responses = ProviderRegistry(
        settings_with(
            ModelProfileSettings(
                id="azure:responses",
                provider="azure-openai-responses",
                base_url="https://resource.services.ai.azure.com/openai/v1",
                model="gpt-5.6-sol",
                api_key_env="TEST_MODEL_KEY",
            )
        )
    ).create("azure:responses")
```

Then add:

```python
    assert isinstance(responses, AzureOpenAIResponsesProvider)
```

- [ ] **Step 6: Run the registry test and verify unsupported provider failure**

Run:

```bash
cd apps/api
pytest tests/extraction/test_providers.py::test_registry_builds_all_supported_providers -v
```

Expected: FAIL with `ProviderError: UNSUPPORTED_PROVIDER`.

- [ ] **Step 7: Register the new extraction provider**

Add this branch to `ProviderRegistry.create()` in `apps/api/src/app/extraction/providers.py`, immediately after the existing `azure-openai` branch:

```python
        if profile.provider == "azure-openai-responses":
            from app.extraction.azure_responses import AzureOpenAIResponsesProvider

            return AzureOpenAIResponsesProvider(
                base_url=profile.base_url,
                model=profile.model,
                api_key=self.secret_for(profile) or "",
                timeout_seconds=profile.timeout_seconds,
            )
```

- [ ] **Step 8: Run extraction provider tests**

Run:

```bash
cd apps/api
pytest tests/extraction/test_azure_responses_client.py tests/extraction/test_provider_contracts.py tests/extraction/test_providers.py -v
```

Expected: all tests pass, including existing providers.

- [ ] **Step 9: Commit the extraction adapter**

```bash
git add apps/api/src/app/extraction/azure_responses.py apps/api/src/app/extraction/providers.py apps/api/tests/extraction/test_provider_contracts.py apps/api/tests/extraction/test_providers.py
git commit -m "feat: extract graphs with Azure Responses"
```

---

### Task 3: QA intent adapter

**Files:**
- Modify: `apps/api/src/app/qa/llm.py`
- Modify: `apps/api/src/app/extraction/providers.py`
- Modify: `apps/api/tests/qa/test_llm.py`
- Modify: `apps/api/tests/extraction/test_providers.py`

**Interfaces:**
- Consumes: `AzureResponsesClient.generate_structured(...) -> str` from Task 1.
- Produces: `QaResponsesIntentProvider.parse(question: str, catalog: OntologyCatalog) -> QaIntent` and registry selection for QA profile kind `azure-openai-responses`.

- [ ] **Step 1: Write the failing Responses QA contract test**

Add this import to `apps/api/tests/qa/test_llm.py`:

```python
import app.qa.llm as qa_llm
```

Add this helper and test:

```python
def responses_provider(client):
    return qa_llm.QaResponsesIntentProvider(
        base_url="https://resource.services.ai.azure.com/openai/v1",
        model="gpt-5.6-sol",
        api_key="secret",
        client=client,
    )


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
    client = FakeClient(
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": content}],
                }
            ],
        }
    )

    intent = responses_provider(client).parse("令狐冲的性别是什么？", CATALOG)

    assert intent.property == "gender"
    url, request = client.requests[0]
    assert url.endswith("/openai/v1/responses")
    assert request["headers"]["Authorization"] == "Bearer secret"
    assert request["json"]["text"]["format"]["name"] == "qa_intent"
    assert "gender" in request["json"]["input"][0]["content"]
```

- [ ] **Step 2: Run the QA test and verify the missing class failure**

Run:

```bash
cd apps/api
pytest tests/qa/test_llm.py::test_responses_provider_parses_intent_and_uses_native_schema -v
```

Expected: the test fails with
`AttributeError: module 'app.qa.llm' has no attribute 'QaResponsesIntentProvider'`.

- [ ] **Step 3: Extract shared QA constraint and validation helpers**

In `apps/api/src/app/qa/llm.py`, add these module-level helpers after `MIN_CONFIDENCE`:

```python
def _allowed_ids(catalog: OntologyCatalog) -> tuple[list[str], list[str]]:
    relation_ids = [item.id.value for item in catalog.relation_types]
    property_ids = sorted(
        {
            prop.id
            for entity in catalog.entity_types
            for prop in entity.effective_property_definitions
        }
    )
    return relation_ids, property_ids


def _validate_intent(
    intent: QaIntent, relation_ids: list[str], property_ids: list[str]
) -> QaIntent:
    if intent.confidence < MIN_CONFIDENCE:
        raise ProviderError(
            ProviderErrorKind.INVALID_RESPONSE, "QA_INTENT_LOW_CONFIDENCE"
        )
    if intent.relation is not None and intent.relation not in relation_ids:
        raise ProviderError(ProviderErrorKind.INVALID_RESPONSE, "QA_INTENT_INVALID")
    if intent.property is not None and intent.property not in property_ids:
        raise ProviderError(ProviderErrorKind.INVALID_RESPONSE, "QA_INTENT_INVALID")
    return intent
```

Update the start of `QaIntentProvider.parse()` to:

```python
        relation_ids, property_ids = _allowed_ids(catalog)
```

Replace its final confidence and allowlist checks with:

```python
        return _validate_intent(intent, relation_ids, property_ids)
```

- [ ] **Step 4: Run existing QA tests after the internal refactor**

Run only the existing cases:

```bash
cd apps/api
pytest tests/qa/test_llm.py::test_parses_strict_intent_and_sends_allowlist tests/qa/test_llm.py::test_rejects_unknown_relation_and_low_confidence tests/qa/test_llm.py::test_maps_http_and_json_failures_to_provider_errors -v
```

Expected: the three existing tests pass.

- [ ] **Step 5: Implement the Responses QA adapter**

Add the import in `apps/api/src/app/qa/llm.py`:

```python
from app.extraction.azure_responses_client import AzureResponsesClient
```

Add this class after `QaIntentProvider`:

```python
class QaResponsesIntentProvider:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str,
        timeout_seconds: float = 30,
        client: httpx.Client | None = None,
    ) -> None:
        self.responses = AzureResponsesClient(
            base_url=base_url,
            model=model,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            client=client,
        )

    def parse(self, question: str, catalog: OntologyCatalog) -> QaIntent:
        relation_ids, property_ids = _allowed_ids(catalog)
        content = self.responses.generate_structured(
            messages=[
                {
                    "role": "system",
                    "content": QaIntentProvider._system_prompt(
                        relation_ids, property_ids
                    ),
                },
                {"role": "user", "content": question},
            ],
            format_name="qa_intent",
            schema=QaIntentProvider._schema(relation_ids, property_ids),
        )
        try:
            intent = QaIntent.model_validate_json(content)
        except (TypeError, ValueError, ValidationError) as error:
            raise ProviderError(
                ProviderErrorKind.INVALID_RESPONSE, "MODEL_RESPONSE_INVALID"
            ) from error
        return _validate_intent(intent, relation_ids, property_ids)
```

- [ ] **Step 6: Run all QA tests**

Run:

```bash
cd apps/api
pytest tests/qa/test_llm.py -v
```

Expected: all QA provider tests pass.

- [ ] **Step 7: Add a Responses-specific validation regression test**

Append this test to `apps/api/tests/qa/test_llm.py`:

```python
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
    client = FakeClient(
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": content}],
                }
            ],
        }
    )

    with pytest.raises(ProviderError, match="QA_INTENT_LOW_CONFIDENCE"):
        responses_provider(client).parse("令狐冲的性别是什么？", CATALOG)
```

Run:

```bash
cd apps/api
pytest tests/qa/test_llm.py -v
```

Expected: all QA tests pass, including the Responses validation case.

- [ ] **Step 8: Write the failing QA registry test**

Add `QaResponsesIntentProvider` to the imports in
`apps/api/tests/extraction/test_providers.py`, then add:

```python
def test_registry_builds_responses_qa_provider(monkeypatch):
    monkeypatch.setenv("TEST_MODEL_KEY", "secret")
    registry = ProviderRegistry(
        settings_with(
            ModelProfileSettings(
                id="azure:responses",
                provider="azure-openai-responses",
                base_url="https://resource.services.ai.azure.com/openai/v1",
                model="gpt-5.6-sol",
                api_key_env="TEST_MODEL_KEY",
            )
        )
    )

    result = registry.create_qa_intent("azure:responses")

    assert isinstance(result, QaResponsesIntentProvider)
```

- [ ] **Step 9: Run the registry test and verify unsupported profile failure**

Run:

```bash
cd apps/api
pytest tests/extraction/test_providers.py::test_registry_builds_responses_qa_provider -v
```

Expected: FAIL with `QA_MODEL_PROFILE_UNSUPPORTED`.

- [ ] **Step 10: Extend QA registry selection**

Replace `ProviderRegistry.create_qa_intent()` in
`apps/api/src/app/extraction/providers.py` with:

```python
    def create_qa_intent(self, profile_id: str):
        profile = self.profile(profile_id)
        if profile.provider == "azure-openai":
            from app.qa.llm import QaIntentProvider

            return QaIntentProvider(
                base_url=profile.base_url,
                deployment=profile.model,
                api_version=profile.api_version,
                api_key=self.secret_for(profile) or "",
                timeout_seconds=profile.timeout_seconds,
            )
        if profile.provider == "azure-openai-responses":
            from app.qa.llm import QaResponsesIntentProvider

            return QaResponsesIntentProvider(
                base_url=profile.base_url,
                model=profile.model,
                api_key=self.secret_for(profile) or "",
                timeout_seconds=profile.timeout_seconds,
            )
        raise ProviderError(
            ProviderErrorKind.CONFIGURATION, "QA_MODEL_PROFILE_UNSUPPORTED"
        )
```

- [ ] **Step 11: Run extraction and QA registry tests**

Run:

```bash
cd apps/api
pytest tests/extraction/test_providers.py tests/qa/test_llm.py -v
```

Expected: all tests pass, including both Azure QA adapters.

- [ ] **Step 12: Commit the QA adapter**

```bash
git add apps/api/src/app/qa/llm.py apps/api/src/app/extraction/providers.py apps/api/tests/qa/test_llm.py apps/api/tests/extraction/test_providers.py
git commit -m "feat: parse QA intents with Azure Responses"
```

---

### Task 4: Environment and deployment documentation

**Files:**
- Modify: `.env.example`
- Modify: `compose.yaml`
- Modify: `docs/deployment-docker-azure-openai.md`

**Interfaces:**
- Consumes: profile kind `azure-openai-responses` and `QA_MODEL_PROFILE_ID` from Tasks 2 and 3.
- Produces: copy-safe operator configuration and verification commands.

- [ ] **Step 1: Add the Responses profile to `.env.example`**

Change `MODEL_PROFILES_JSON` to include this profile object in the existing
single-line array:

```json
{"id":"azure:gpt-5.6-sol","provider":"azure-openai-responses","base_url":"https://YOUR_RESOURCE.services.ai.azure.com/openai/v1","model":"YOUR_RESPONSES_DEPLOYMENT_NAME","api_key_env":"AZURE_OPENAI_API_KEY","timeout_seconds":180}
```

Add immediately below the profile configuration:

```dotenv
# Select a profile that supports QA intent parsing: azure-openai or azure-openai-responses.
QA_MODEL_PROFILE_ID=azure:gpt-5.6-sol
```

Keep `AZURE_OPENAI_API_KEY=replace-with-your-azure-key` as a non-secret example.

- [ ] **Step 2: Pass the QA profile selector through Docker Compose**

Add this entry to the shared `x-app-env` mapping in `compose.yaml`:

```yaml
  QA_MODEL_PROFILE_ID: ${QA_MODEL_PROFILE_ID:-azure:gpt-4o-mini}
```

This keeps the current default while allowing `.env` to select
`azure:gpt-5.6-sol` inside the API container.

- [ ] **Step 3: Document the two Azure API styles**

Add a section titled `Azure v1 Responses 模型` to
`docs/deployment-docker-azure-openai.md` containing this exact example:

```dotenv
AZURE_OPENAI_API_KEY=replace-with-your-azure-openai-key
MODEL_PROFILES_JSON=[{"id":"fixed:test","provider":"fixed","base_url":"","model":"deterministic-test","api_key_env":"","timeout_seconds":10},{"id":"azure:gpt-5.6-sol","provider":"azure-openai-responses","base_url":"https://dxp-5099-resource.services.ai.azure.com/openai/v1","model":"gpt-5.6-sol","api_key_env":"AZURE_OPENAI_API_KEY","timeout_seconds":180}]
QA_MODEL_PROFILE_ID=azure:gpt-5.6-sol
```

Explain these rules directly below the example:

```markdown
- Azure 门户显示的完整 Endpoint 可能以 `/openai/v1/responses` 结尾；`base_url` 只填写到 `/openai/v1`。
- `model` 必须填写 Deployment info 中的 Name。
- `azure-openai-responses` 不填写 `api_version`，不会调用旧的 deployment-scoped Chat Completions URL。
- `QA_MODEL_PROFILE_ID` 指向该 profile 后，同一个 deployment 也用于问答意图解析。
- 原有 `azure-openai` profile 仍用于 `/chat/completions`，两种 profile 可以同时存在。
```

- [ ] **Step 4: Add safe deployment verification commands**

Add these commands to the same section:

```bash
sudo docker compose config >/dev/null
sudo docker compose up -d --build api worker
sudo docker compose exec worker printenv MODEL_PROFILES_JSON
sudo docker compose exec api printenv QA_MODEL_PROFILE_ID
sudo docker compose exec worker sh -c 'test -n "$AZURE_OPENAI_API_KEY" && echo AZURE_OPENAI_API_KEY=set'
curl -s http://localhost:5173/api/model-profiles
```

Add this direct endpoint smoke test after the container checks. It reads the
key from the current shell and never prints the key itself:

```bash
AZURE_RESPONSES_ENDPOINT=https://dxp-5099-resource.services.ai.azure.com/openai/v1
curl --fail-with-body --silent --show-error \
  "${AZURE_RESPONSES_ENDPOINT}/responses" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${AZURE_OPENAI_API_KEY}" \
  -d '{"model":"gpt-5.6-sol","input":"只回答 OK。","store":false}'
```

Document the expected results:

```markdown
- Compose 配置校验无错误。
- Worker 的 profile 中包含 `azure-openai-responses`、`/openai/v1` 和正确 deployment name。
- API 的 `QA_MODEL_PROFILE_ID` 等于新 profile ID。
- 密钥检查只输出 `AZURE_OPENAI_API_KEY=set`，不会显示密钥值。
- `/api/model-profiles` 中新 profile 的 `available` 为 `true`。
- 直接 smoke test 返回 HTTP 2xx，响应顶层 `status` 为 `completed`，且
  `output` 中包含模型文本。
```

- [ ] **Step 5: Verify documentation contains no real secret**

Run:

```bash
rg -n "sk-[A-Za-z0-9_-]{20,}|Bearer [A-Za-z0-9_-]{20,}" .env.example docs/deployment-docker-azure-openai.md
```

Expected: no matches.

- [ ] **Step 6: Verify documented provider and endpoint consistency**

Run:

```bash
rg -n "azure-openai-responses|QA_MODEL_PROFILE_ID|/openai/v1" .env.example docs/deployment-docker-azure-openai.md
```

Expected: both files contain the new provider, QA selector, and base URL shape.

- [ ] **Step 7: Commit configuration and documentation**

```bash
git add .env.example compose.yaml docs/deployment-docker-azure-openai.md
git commit -m "docs: configure Azure Responses deployments"
```

---

### Task 5: Full regression and delivery verification

**Files:**
- Verify only; modify files solely to correct failures attributable to Tasks 1-4.

**Interfaces:**
- Consumes: all prior task outputs.
- Produces: a release-ready branch with passing API and Compose checks.

- [ ] **Step 1: Run focused Responses, provider, and QA tests**

Run:

```bash
cd apps/api
pytest tests/extraction/test_azure_responses_client.py tests/extraction/test_provider_contracts.py tests/extraction/test_providers.py tests/qa/test_llm.py -v
```

Expected: all focused tests pass.

- [ ] **Step 2: Run the complete API test suite**

Run:

```bash
cd apps/api
pytest -q
```

Expected: exit code 0 with no failures.

- [ ] **Step 3: Validate Docker Compose expansion**

Run from the repository root:

```bash
docker compose config >/dev/null
```

Expected: exit code 0 and no interpolation or JSON quoting errors.

- [ ] **Step 4: Run static repository hygiene checks**

Run:

```bash
git diff --check master...HEAD
rg -n "AZURE_OPENAI_API_KEY=.+|Authorization: Bearer [A-Za-z0-9_-]{12,}" --glob '!docs/superpowers/plans/*.md' --glob '!*.example' .
```

Expected: `git diff --check` produces no output; secret scan produces no real credential matches. Review any match before continuing because documentation may contain deliberate placeholder text.

- [ ] **Step 5: Review the final change set against the approved design**

Run:

```bash
git status --short
git diff --stat master...HEAD
git log --oneline master..HEAD
```

Expected: only the approved provider, tests, `.env.example`, deployment guide,
design, and plan changes are present; commits are scoped and ordered.

- [ ] **Step 6: Commit any verification-only corrections**

If Step 1-5 required a correction, stage only the affected files and commit:

```bash
git add apps/api .env.example compose.yaml docs/deployment-docker-azure-openai.md
git commit -m "fix: complete Azure Responses verification"
```

If no correction was required, do not create an empty commit.
