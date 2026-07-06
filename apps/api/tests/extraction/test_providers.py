import pytest

from app.extraction.fixed import FixedProvider
from app.extraction.ollama import OllamaProvider
from app.extraction.openai_compatible import OpenAICompatibleProvider
from app.extraction.providers import ProviderError, ProviderRegistry
from app.settings import ModelProfileSettings, Settings


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
    ollama = ProviderRegistry(
        settings_with(ModelProfileSettings(
            id="ollama:test", provider="ollama", base_url="http://fake", model="qwen3"
        ))
    ).create("ollama:test")
    fixed = ProviderRegistry(
        settings_with(ModelProfileSettings(id="fixed:test", provider="fixed", model="test"))
    ).create("fixed:test")
    assert isinstance(openai, OpenAICompatibleProvider)
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
