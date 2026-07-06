from enum import StrEnum
import os
from typing import Protocol

from app.extraction.models import ExtractionRequest, ExtractionResult
from app.settings import ModelProfileSettings, Settings


class ProviderErrorKind(StrEnum):
    RETRYABLE = "RETRYABLE"
    CONFIGURATION = "CONFIGURATION"
    INVALID_RESPONSE = "INVALID_RESPONSE"


class ProviderError(RuntimeError):
    def __init__(self, kind: ProviderErrorKind, code: str) -> None:
        super().__init__(code)
        self.kind = kind
        self.code = code


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
        if profile.provider == "ollama":
            from app.extraction.ollama import OllamaProvider

            return OllamaProvider(
                base_url=profile.base_url,
                model=profile.model,
                timeout_seconds=profile.timeout_seconds,
            )
        raise ProviderError(ProviderErrorKind.CONFIGURATION, "UNSUPPORTED_PROVIDER")
