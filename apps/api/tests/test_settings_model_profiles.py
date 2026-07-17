import pytest
from pydantic import ValidationError

from app.settings import ModelProfileSettings


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
