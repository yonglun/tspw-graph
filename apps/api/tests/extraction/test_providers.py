import pytest

from app.extraction.fixed import FixedProvider
from app.extraction.models import ExtractionRequest
from app.extraction.azure_openai import AzureOpenAIProvider
from app.extraction.azure_responses import AzureOpenAIResponsesProvider
from app.extraction.ollama import OllamaProvider
from app.extraction.openai_compatible import OpenAICompatibleProvider
from app.extraction.providers import ProviderError, ProviderRegistry
from app.settings import ModelProfileSettings, Settings
from app.qa.llm import QaResponsesIntentProvider


def settings_with(profile: ModelProfileSettings) -> Settings:
    return Settings(model_profiles=[profile])


def test_registry_builds_all_supported_providers(monkeypatch):
    monkeypatch.setenv("TEST_MODEL_KEY", "secret")
    openai = ProviderRegistry(
        settings_with(ModelProfileSettings(
            id="openai:test", provider="openai-compatible", base_url="http://fake/v1",
            model="demo", api_key_env="TEST_MODEL_KEY"
        ))
    ).create("openai:test")
    azure = ProviderRegistry(
        settings_with(ModelProfileSettings(
            id="azure:test", provider="azure-openai", base_url="https://fake.openai.azure.com",
            model="deployment", api_key_env="TEST_MODEL_KEY", api_version="2024-06-01"
        ))
    ).create("azure:test")
    responses = ProviderRegistry(
        settings_with(ModelProfileSettings(
            id="azure:responses", provider="azure-openai-responses",
            base_url="https://resource.services.ai.azure.com/openai/v1",
            model="gpt-5.6-sol", api_key_env="TEST_MODEL_KEY"
        ))
    ).create("azure:responses")
    ollama = ProviderRegistry(
        settings_with(ModelProfileSettings(
            id="ollama:test", provider="ollama", base_url="http://fake", model="qwen3"
        ))
    ).create("ollama:test")
    fixed = ProviderRegistry(
        settings_with(ModelProfileSettings(id="fixed:test", provider="fixed", model="test"))
    ).create("fixed:test")
    assert isinstance(openai, OpenAICompatibleProvider)
    assert isinstance(azure, AzureOpenAIProvider)
    assert isinstance(responses, AzureOpenAIResponsesProvider)
    assert isinstance(ollama, OllamaProvider)
    assert isinstance(fixed, FixedProvider)


def test_registry_rejects_missing_secret(monkeypatch):
    monkeypatch.delenv("MISSING_KEY", raising=False)
    registry = ProviderRegistry(settings_with(ModelProfileSettings(
        id="openai:test", provider="openai-compatible", base_url="http://fake/v1",
        model="demo", api_key_env="MISSING_KEY"
    )))
    with pytest.raises(ProviderError, match="MODEL_API_KEY_MISSING"):
        registry.create("openai:test")


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
                reasoning_effort="low",
                max_output_tokens=12000,
            )
        )
    )

    result = registry.create_qa_intent("azure:responses")

    assert isinstance(result, QaResponsesIntentProvider)
    assert result.responses.reasoning_effort == "low"
    assert result.responses.max_output_tokens == 12000


def test_registry_passes_responses_performance_controls(monkeypatch):
    monkeypatch.setenv("TEST_MODEL_KEY", "secret")
    registry = ProviderRegistry(
        settings_with(
            ModelProfileSettings(
                id="azure:responses",
                provider="azure-openai-responses",
                base_url="https://resource.services.ai.azure.com/openai/v1",
                model="gpt-5.6-sol",
                api_key_env="TEST_MODEL_KEY",
                reasoning_effort="low",
                max_output_tokens=12000,
            )
        )
    )

    result = registry.create("azure:responses")

    assert isinstance(result, AzureOpenAIResponsesProvider)
    assert result.responses.reasoning_effort == "low"
    assert result.responses.max_output_tokens == 12000


def test_fixed_provider_extracts_deterministic_e2e_fixture():
    text = "第一章 相遇\n测试人物甲认识测试人物乙。"
    result = FixedProvider().extract(ExtractionRequest(
        project_id="project-1", chunk_id="chunk-1", text=text, ontology={}
    ))

    assert [entity.name for entity in result.entities] == ["测试人物甲", "测试人物乙"]
    assert result.facts[0].relation == "KNOWS"
    evidence = result.facts[0].evidence
    assert text[evidence.start:evidence.end] == evidence.quote
