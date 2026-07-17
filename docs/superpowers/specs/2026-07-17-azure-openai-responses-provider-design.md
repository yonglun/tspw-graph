# Azure OpenAI Responses Provider Design

## Status

Approved for implementation on 2026-07-17.

## Goal

Add first-class support for Azure OpenAI v1 Responses API deployments such as
`gpt-5.6-sol`. The deployment must be usable for both knowledge-graph extraction
and QA intent parsing without changing the behavior of existing Chat
Completions, OpenAI-compatible, Ollama, or fixed providers.

## Scope

This change adds a new provider kind, `azure-openai-responses`, alongside the
existing `azure-openai` provider. It supports API-key authentication only in the
first release.

In scope:

- Structured information extraction through the Responses API.
- Structured QA intent parsing through the Responses API.
- Provider registration and environment configuration.
- Existing retry, content-filter, validation, and secret-handling behavior.
- Automated contract, parsing, error, registry, QA, and regression tests.
- `.env.example` and Docker deployment documentation.

Out of scope:

- Microsoft Entra ID authentication.
- Replacing or changing the existing `azure-openai` provider.
- Frontend, database, chunking, graph-import, or task-state changes.
- Streaming Responses API calls, tool calls, or conversation persistence.

## Architecture

### Provider coexistence

The provider registry continues to select implementations using the profile's
`provider` field:

- `azure-openai` uses deployment-scoped Chat Completions URLs.
- `azure-openai-responses` uses the OpenAI-compatible Azure v1 Responses URL.

The new provider does not infer API behavior from the endpoint string. An
explicit provider kind keeps configuration behavior visible and prevents an
endpoint change from silently selecting a different protocol.

### Shared Responses client

Add a small shared `AzureResponsesClient` responsible only for the Responses
transport contract:

- Append `/responses` to a normalized `base_url`.
- Authenticate with `Authorization: Bearer <API_KEY>`.
- Send a model deployment name, input messages, a strict structured-output
  schema, and `store: false`.
- Extract ordered `output_text` content from completed message output.
- Map HTTP, Azure rate-limit, content-filter, refusal, incomplete, and malformed
  responses into the existing `ProviderError` contract.

The client does not know about graph entities or QA intents. Consumers supply a
format name and JSON Schema and validate the returned JSON themselves.

### Extraction adapter

Add `AzureOpenAIResponsesProvider`, implementing the existing
`ExtractionProvider` protocol. It:

1. Reuses `extraction_system_prompt(request)`.
2. Sends the system prompt and serialized `ExtractionRequest` through the
   shared Responses client.
3. Uses `strict_extraction_schema()` as the structured-output schema.
4. Validates the returned JSON as `ExtractionResult`.

The extraction pipeline, normalization, retry loop, progress reporting, and
Neo4j importer remain unchanged.

### QA intent adapter

Add a Responses-based QA intent provider implementing the same public
`parse(question, catalog) -> QaIntent` interface as the existing provider. It:

1. Reuses the current relation and property allowlists.
2. Reuses the current QA system prompt and strict intent schema.
3. Sends the prompt and question through the shared Responses client.
4. Preserves confidence, relation, and property validation.

`ProviderRegistry.create_qa_intent()` selects the existing Chat Completions QA
adapter for `azure-openai` and the new QA adapter for
`azure-openai-responses`.

## Configuration

The Azure portal endpoint includes `/openai/v1/responses`, while the configured
`base_url` stops at `/openai/v1`. The shared client owns the final `/responses`
path component.

Example `.env` configuration:

```dotenv
AZURE_OPENAI_API_KEY=replace-with-your-azure-key

MODEL_PROFILES_JSON=[{"id":"fixed:test","provider":"fixed","base_url":"","model":"deterministic-test","api_key_env":"","timeout_seconds":10},{"id":"azure:gpt-5.6-sol","provider":"azure-openai-responses","base_url":"https://dxp-5099-resource.services.ai.azure.com/openai/v1","model":"gpt-5.6-sol","api_key_env":"AZURE_OPENAI_API_KEY","timeout_seconds":180}]

QA_MODEL_PROFILE_ID=azure:gpt-5.6-sol
```

Configuration semantics:

- `id` is the application profile identifier.
- `provider` must be `azure-openai-responses`.
- `base_url` must end at `/openai/v1`, without `/responses`.
- `model` is the Azure deployment name, not a generic model family alias.
- `api_key_env` names the environment variable containing the secret.
- `timeout_seconds` controls the HTTP client timeout.
- `api_version` is not sent by this v1 provider.
- `QA_MODEL_PROFILE_ID` selects the same profile for QA intent parsing.

The API may expose profile metadata and availability but must never expose the
secret value. The Worker and API resolve the secret through `api_key_env` using
the existing settings mechanism.

## Request Contract

The extraction request uses the native Responses structured-output shape:

```json
{
  "model": "gpt-5.6-sol",
  "input": [
    {
      "role": "system",
      "content": "<extraction system prompt>"
    },
    {
      "role": "user",
      "content": "<serialized extraction request>"
    }
  ],
  "text": {
    "format": {
      "type": "json_schema",
      "name": "knowledge_graph_extraction",
      "strict": true,
      "schema": {}
    }
  },
  "store": false
}
```

The QA request uses the same envelope with format name `qa_intent`, the QA
intent schema, the current QA system prompt, and the user's question.

The provider does not send `temperature`, legacy `response_format`, a
deployment-scoped URL, or an `api-version` query parameter.

## Response Contract

The client accepts only a response whose top-level status is `completed` and
whose output contains at least one message content item of type `output_text`.
It collects matching text items in response order and concatenates them before
consumer validation.

The client ignores unrelated tool or reasoning output items. It rejects:

- A top-level status of `incomplete`, `failed`, `cancelled`, `queued`, or
  `in_progress` for the synchronous request.
- Any refusal content.
- A response with no `output_text`.
- Malformed response envelopes.

Extraction and QA consumers then validate the resulting text against their
Pydantic models. Invalid JSON and schema violations use the existing invalid
response behavior.

## Error Handling

The adapter preserves the existing `ProviderError` abstraction.

| Condition | Kind | Error code | Retry |
| --- | --- | --- | --- |
| HTTP 401, 403, 404 | `CONFIGURATION` | `MODEL_HTTP_<status>` | No |
| HTTP 408, 409, 429 | `RETRYABLE` | `MODEL_HTTP_<status>` | Yes |
| HTTP 5xx | `RETRYABLE` | `MODEL_HTTP_<status>` | Yes |
| Other HTTP 4xx | `CONFIGURATION` | `MODEL_HTTP_<status>` | No |
| Azure content filter | `INVALID_RESPONSE` | `MODEL_CONTENT_FILTER` | No |
| Incomplete synchronous response | `INVALID_RESPONSE` | `MODEL_RESPONSE_INCOMPLETE` | No |
| Refusal content | `INVALID_RESPONSE` | `MODEL_RESPONSE_REFUSED` | No |
| Missing output or malformed JSON | `INVALID_RESPONSE` | `MODEL_RESPONSE_INVALID` | No |
| Network or transport failure | `RETRYABLE` | `MODEL_NETWORK_ERROR` | Yes |

Retry delays preserve `retry-after-ms`, `x-ms-retry-after-ms`, and
`retry-after` through the current parser.

Logs may include HTTP status, profile or deployment name, and a length-limited
response excerpt. Logs must not include API keys, authorization headers, or the
complete source text.

## Compatibility

- Existing profile JSON remains valid.
- Existing provider behavior and URLs do not change.
- Existing build and QA interfaces remain stable.
- The frontend discovers the new profile through the existing model-profile
  endpoint and requires no new component.
- Existing Docker Compose secret propagation is sufficient because the new
  profile reuses `AZURE_OPENAI_API_KEY`.
- No database migration is required.

## Testing

### Transport contract

- Verify the request path ends with `/openai/v1/responses`.
- Verify Bearer authentication and absence of the legacy `api-key` header.
- Verify `model`, `input`, `text.format`, strict JSON Schema, and `store: false`.
- Verify absence of `temperature`, `response_format`, and `api-version`.

### Response parsing

- Parse one `output_text` item.
- Concatenate multiple ordered `output_text` items.
- Ignore unrelated output types.
- Reject refusal, empty output, incomplete status, and malformed envelopes.
- Validate extraction and QA JSON through their existing Pydantic models.

### Error behavior

- Verify configuration and retryable HTTP mappings.
- Verify Azure retry headers are preserved.
- Verify content-filter mapping.
- Verify logs do not contain the API key.

### Registry and QA

- Verify extraction registry creation for `azure-openai-responses`.
- Verify QA registry creation for `azure-openai-responses`.
- Verify existing provider registry cases continue to pass.
- Verify relation/property allowlists and confidence checks remain effective.

### Regression and documentation

- Run the complete API test suite.
- Validate Docker Compose configuration expansion.
- Update `.env.example` and the Docker Azure deployment guide.
- Document container environment checks and a minimal Responses API smoke test
  that does not print the key.

## Acceptance Criteria

1. A profile configured with the Azure `/openai/v1` endpoint and deployment
   name can complete a structured extraction request.
2. The same profile can serve QA intent parsing when selected by
   `QA_MODEL_PROFILE_ID`.
3. Existing Azure Chat Completions profiles continue to work unchanged.
4. Rate-limit retry metadata reaches the existing pipeline.
5. Invalid, refused, filtered, or incomplete responses fail with explicit error
   codes and do not write partial graph data.
6. No secret appears in API responses, logs, tests, or committed configuration.
7. The full API test suite passes.

## Authoritative References

- Microsoft, Azure OpenAI Responses REST reference:
  <https://learn.microsoft.com/en-us/rest/api/microsoft-foundry/azureopenai/responses>
- Microsoft, migrate Chat Completions to Responses:
  <https://learn.microsoft.com/en-us/azure/developer/ai/how-to/azure-openai-to-responses>

