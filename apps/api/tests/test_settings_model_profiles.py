import pytest
from pydantic import ValidationError

from app.settings import ModelProfileSettings, Settings


def test_extraction_concurrency_defaults_to_one(monkeypatch):
    monkeypatch.delenv("EXTRACTION_CONCURRENCY", raising=False)

    assert Settings(_env_file=None).extraction_concurrency == 1


def test_extraction_concurrency_reads_environment(monkeypatch):
    monkeypatch.setenv("EXTRACTION_CONCURRENCY", "4")

    assert Settings(_env_file=None).extraction_concurrency == 4


@pytest.mark.parametrize("value", ["0", "-1", "17"])
def test_extraction_concurrency_rejects_out_of_range(monkeypatch, value):
    monkeypatch.setenv("EXTRACTION_CONCURRENCY", value)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_responses_profile_accepts_performance_controls():
    profile = ModelProfileSettings(
        id="azure:gpt-5.6-sol",
        provider="azure-openai-responses",
        base_url="https://resource.services.ai.azure.com/openai/v1",
        model="gpt-5.6-sol",
        reasoning_effort="low",
        max_output_tokens=12000,
    )

    assert profile.reasoning_effort == "low"
    assert profile.max_output_tokens == 12000


@pytest.mark.parametrize("max_output_tokens", [0, -1])
def test_responses_profile_rejects_non_positive_output_limit(max_output_tokens):
    with pytest.raises(ValidationError):
        ModelProfileSettings(
            id="azure:gpt-5.6-sol",
            provider="azure-openai-responses",
            model="gpt-5.6-sol",
            max_output_tokens=max_output_tokens,
        )
