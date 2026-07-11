# LLM Intent and Attribute QA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend explainable QA with ontology-attribute answers, broader relation question parsing, and Azure OpenAI intent fallback while keeping all graph queries allowlisted and evidence-backed.

**Architecture:** Keep a deterministic local parser as the fast path. When it returns no safe intent, call a server-side Azure OpenAI provider that returns a strict intent JSON object; validate it against the ontology catalog and resolve the subject through the existing project-scoped search. Execute only fixed relation/attribute lookups through the graph repository and return evidence, never model-generated facts.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, httpx, Neo4j, pytest, React/TypeScript, Vitest, existing `ModelProfileSettings` and Azure OpenAI provider.

## Global Constraints

- LLM output is an intent only; it must never contain executable Cypher or the final factual answer.
- Relation IDs and property IDs must come from the ontology catalog allowlists.
- Every successful answer must include graph-backed evidence; otherwise return the existing explicit refusal.
- Existing fixed relation questions must remain functional when Azure is unavailable.
- Frontend must never receive or store API keys.
- Do not change entity, fact, attribute, evidence, or review persistence schemas.

---

### Task 1: Add typed QA intents and deterministic normalization

**Files:**
- Create: `apps/api/src/app/qa/intents.py`
- Modify: `apps/api/src/app/qa/templates.py`
- Test: `apps/api/tests/qa/test_intents.py`
- Test: `apps/api/tests/qa/test_service.py`

**Interfaces:**
- `QaIntent`: `intent`, `subject`, `relation`, `property`, and `confidence`.
- `parse_local_intent(question: str) -> QaIntent | None`.
- `normalize_question(question: str) -> str` and `extract_subject(question: str, markers: tuple[str, ...]) -> str | None`.

- [ ] **Step 1: Write failing parser tests.** Cover `令狐冲隶属于什么门派？`, `令狐冲属于哪个门派？`, `令狐冲的性别是什么？`, `令狐冲有哪些称号？`, existing师父 wording, and an unsupported birthday question. Assert exact intent, relation/property ID, and subject.
- [ ] **Step 2: Run the parser tests.** Run `pytest apps/api/tests/qa/test_intents.py -q`; expect failure because the parser functions do not exist.
- [ ] **Step 3: Implement local parsing.** Add synonym tables for `MASTER_OF`, `MEMBER_OF`, `KNOWS`, `ENEMY_OF`, `ALLY_OF`, `HOLDS`, `OCCURS_AT`, and `gender`, `identity`, `honorific`, `life_status`, `activity_region`, `region`, `characteristic`. Normalize simplified/traditional punctuation and strip prefixes/suffixes before extracting the subject.
- [ ] **Step 4: Run parser and regression tests.** Run `pytest apps/api/tests/qa/test_intents.py apps/api/tests/qa/test_service.py -q`; expect all pass.
- [ ] **Step 5: Commit.** Run `git add apps/api/src/app/qa/intents.py apps/api/src/app/qa/templates.py apps/api/tests/qa/test_intents.py apps/api/tests/qa/test_service.py && git commit -m "feat: add deterministic QA intent parsing"`.

### Task 2: Add strict Azure OpenAI intent fallback

**Files:**
- Create: `apps/api/src/app/qa/llm.py`
- Modify: `apps/api/src/app/extraction/providers.py`
- Modify: `apps/api/src/app/settings.py`
- Test: `apps/api/tests/qa/test_llm.py`

**Interfaces:**
- `QaIntentProvider.parse(question: str, catalog: OntologyCatalog) -> QaIntent`.
- Reuse `ProviderRegistry`, `ModelProfileSettings`, Azure `api-key` authentication, and the existing `ProviderError` taxonomy.
- Add `qa_model_profile_id: str = "azure:gpt-4o-mini"` with environment override `QA_MODEL_PROFILE_ID`.

- [ ] **Step 1: Write failing provider contract tests.** Mock `httpx.Client`; assert the request includes the question, allowlisted IDs, JSON-schema response format, and no secret. Cover valid JSON, unknown relation/property, malformed JSON, low confidence, 429, and content-filter responses.
- [ ] **Step 2: Run `pytest apps/api/tests/qa/test_llm.py -q`; expect failure because the provider and schema do not exist.**
- [ ] **Step 3: Implement the provider.** Send a compact system prompt containing catalog IDs and a strict schema with no extra fields. Convert model failures to `ProviderError`, reject unknown IDs, and reject confidence below `0.70`. Do not log API keys.
- [ ] **Step 4: Run `pytest apps/api/tests/qa/test_llm.py apps/api/tests/test_health.py -q`; expect all pass.**
- [ ] **Step 5: Commit.** Run `git add apps/api/src/app/qa/llm.py apps/api/src/app/extraction/providers.py apps/api/src/app/settings.py apps/api/tests/qa/test_llm.py && git commit -m "feat: add constrained LLM QA intent fallback"`.

### Task 3: Answer attributes and normalized relations in `QaService`

**Files:**
- Modify: `apps/api/src/app/qa/service.py`
- Modify: `apps/api/src/app/qa/models.py`
- Modify: `apps/api/src/app/graph/repository.py` only if a dedicated lookup is needed
- Test: `apps/api/tests/qa/test_service.py`
- Test: `apps/api/tests/qa/test_review_filters.py`

**Interfaces:**
- Keep `QaService(repository, intent_provider: QaIntentProvider | None = None)` compatible with current tests.
- Add an internal attribute path consuming `entity_detail(...)["attributes"]` and returning `AskResponse` with `AttributeDetail` evidence.
- Preserve existing relation direction, path, and evidence behavior.

- [ ] **Step 1: Write failing service tests.** Add fake `gender` and `honorific` attributes with evidence. Assert “令狐冲的性别是什么？” returns “男”, includes evidence, and has no graph path. Add missing/rejected attribute cases that return `NO_FACTS`.
- [ ] **Step 2: Run `pytest apps/api/tests/qa/test_service.py apps/api/tests/qa/test_review_filters.py -q`; expect attribute tests to fail.**
- [ ] **Step 3: Implement local-first fallback flow.** Call `parse_local_intent`; if it returns `None` and a provider exists, call the LLM provider. Validate the subject through exact name/alias matching. For `ATTRIBUTE`, filter by property ID and require non-rejected evidence. For `RELATION`, keep the current relation logic. Provider errors return the existing refusal response.
- [ ] **Step 4: Add relation regression tests.** Assert both “令狐冲隶属于什么门派？” and “令狐冲属于哪个门派？” resolve `MEMBER_OF` and return the organization.
- [ ] **Step 5: Run `pytest apps/api/tests/qa -q`; expect all QA tests to pass.**
- [ ] **Step 6: Commit.** Run `git add apps/api/src/app/qa/service.py apps/api/src/app/qa/models.py apps/api/src/app/graph/repository.py apps/api/tests/qa/test_service.py apps/api/tests/qa/test_review_filters.py && git commit -m "feat: answer graph attributes and normalized relations"`.

### Task 4: Wire the configured intent provider into the API

**Files:**
- Modify: `apps/api/src/app/qa/router.py`
- Test: `apps/api/tests/qa/test_live_api.py`

**Interfaces:**
- Keep `POST /api/ask` request body `{project_id, question}` unchanged.
- Build the provider from server settings; never accept a model profile or API key in the request.

- [ ] **Step 1: Write an API wiring test.** Mock the provider and verify an unrecognized question reaches it while a recognized local question does not. Assert the response schema is unchanged.
- [ ] **Step 2: Implement dependency wiring.** Add a small cached provider factory using `get_settings().qa_model_profile_id` and `ProviderRegistry`; if configuration is unavailable, pass `None` so local templates continue to work.
- [ ] **Step 3: Run `pytest apps/api/tests/qa/test_live_api.py apps/api/tests/qa -q`; expect all pass and provider failures to become refusals, not 500 responses.**
- [ ] **Step 4: Commit.** Run `git add apps/api/src/app/qa/router.py apps/api/tests/qa/test_live_api.py && git commit -m "feat: wire server-side QA intent provider"`.

### Task 5: Update Ask page examples and UI tests

**Files:**
- Modify: `apps/web/src/features/ask/AskPage.tsx`
- Test: `apps/web/src/features/ask/AskPage.test.tsx`

**Interfaces:**
- No API shape change; the existing `AskResponse` drives answer, path, evidence, and technical details.

- [ ] **Step 1: Write failing UI tests.** Assert the sample list contains relation-synonym and attribute examples; mock relation and attribute responses and assert answer text and evidence render.
- [ ] **Step 2: Update samples.** Add `令狐冲属于哪个门派？` and `令狐冲的性别是什么？`, retaining the existing师父 and武学 samples.
- [ ] **Step 3: Run `npm --prefix apps/web test -- --run`, `npm --prefix apps/web run typecheck`, and `npm --prefix apps/web run build`; expect all pass.**
- [ ] **Step 4: Commit.** Run `git add apps/web/src/features/ask/AskPage.tsx apps/web/src/features/ask/AskPage.test.tsx && git commit -m "feat: add attribute and relation QA examples"`.

### Task 6: Full verification and delivery checks

**Files:**
- Modify: none unless a verification regression requires a targeted fix

- [ ] **Step 1: Run focused backend checks.** `pytest apps/api/tests/qa apps/api/tests/ontology -q`; expect all pass with only documented environment-dependent Neo4j skips.
- [ ] **Step 2: Run the full backend suite.** `pytest apps/api/tests -q`; expect no new failures.
- [ ] **Step 3: Run frontend checks.** Run `npm --prefix apps/web test -- --run`, `npm --prefix apps/web run typecheck`, and `npm --prefix apps/web run build`; expect all pass.
- [ ] **Step 4: Run repository checks.** Run `git diff --check` and `git status --short`; expect no whitespace errors and only intentional changes.
- [ ] **Step 5: Verify acceptance scenarios with a configured Azure profile.** Confirm relation synonym, gender attribute, honorific attribute, unsupported question refusal, invalid LLM intent refusal, and fixed-question behavior when Azure is unavailable. Record response evidence IDs.
- [ ] **Step 6: Commit any final targeted test adjustments.** Stage only the affected files and use a descriptive `test:` commit message.

