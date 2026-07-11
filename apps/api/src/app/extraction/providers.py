from enum import StrEnum
import os
from collections.abc import Mapping
from typing import Protocol

from app.extraction.models import ExtractionRequest, ExtractionResult
from app.settings import ModelProfileSettings, Settings


class ProviderErrorKind(StrEnum):
    RETRYABLE = "RETRYABLE"
    CONFIGURATION = "CONFIGURATION"
    INVALID_RESPONSE = "INVALID_RESPONSE"


class ProviderError(RuntimeError):
    def __init__(
        self,
        kind: ProviderErrorKind,
        code: str,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(code)
        self.kind = kind
        self.code = code
        self.retry_after_seconds = retry_after_seconds


def parse_retry_after_seconds(headers: Mapping[str, str]) -> float | None:
    for header_name in ("retry-after-ms", "x-ms-retry-after-ms"):
        value = headers.get(header_name)
        if value is None:
            continue
        try:
            return max(0.0, float(value) / 1000)
        except ValueError:
            return None

    value = headers.get("retry-after")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


class ExtractionProvider(Protocol):
    def extract(self, request: ExtractionRequest) -> ExtractionResult: ...


class ProviderRegistry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def profile(self, profile_id: str) -> ModelProfileSettings:
        for profile in self.settings.model_profiles:
            if profile.id == profile_id:
                return profile
        raise ProviderError(ProviderErrorKind.CONFIGURATION, "UNKNOWN_MODEL_PROFILE")

    def secret_for(self, profile: ModelProfileSettings) -> str | None:
        if not profile.api_key_env:
            return None
        value = os.getenv(profile.api_key_env)
        if not value:
            raise ProviderError(ProviderErrorKind.CONFIGURATION, "MODEL_API_KEY_MISSING")
        return value

    def create(self, profile_id: str) -> ExtractionProvider:
        profile = self.profile(profile_id)
        if profile.provider == "fixed":
            from app.extraction.fixed import FixedProvider

            return FixedProvider()
        if profile.provider == "openai-compatible":
            from app.extraction.openai_compatible import OpenAICompatibleProvider

            return OpenAICompatibleProvider(
                base_url=profile.base_url,
                model=profile.model,
                api_key=self.secret_for(profile) or "",
                timeout_seconds=profile.timeout_seconds,
            )
        if profile.provider == "azure-openai":
            from app.extraction.azure_openai import AzureOpenAIProvider

            return AzureOpenAIProvider(
                base_url=profile.base_url,
                deployment=profile.model,
                api_version=profile.api_version,
                api_key=self.secret_for(profile) or "",
                timeout_seconds=profile.timeout_seconds,
            )
        if profile.provider == "ollama":
            from app.extraction.ollama import OllamaProvider

            return OllamaProvider(
                base_url=profile.base_url,
                model=profile.model,
                timeout_seconds=profile.timeout_seconds,
            )
        raise ProviderError(ProviderErrorKind.CONFIGURATION, "UNSUPPORTED_PROVIDER")

    def create_qa_intent(self, profile_id: str):
        profile = self.profile(profile_id)
        if profile.provider != "azure-openai":
            raise ProviderError(
                ProviderErrorKind.CONFIGURATION, "QA_MODEL_PROFILE_UNSUPPORTED"
            )
        from app.qa.llm import QaIntentProvider

        return QaIntentProvider(
            base_url=profile.base_url,
            deployment=profile.model,
            api_version=profile.api_version,
            api_key=self.secret_for(profile) or "",
            timeout_seconds=profile.timeout_seconds,
        )
