import os

from fastapi import APIRouter
from pydantic import BaseModel

from app.settings import get_settings

router = APIRouter(tags=["models"])


class PublicModelProfile(BaseModel):
    id: str
    provider: str
    base_url: str
    model: str
    timeout_seconds: float
    available: bool


@router.get("/api/model-profiles", response_model=list[PublicModelProfile])
def model_profiles() -> list[PublicModelProfile]:
    return [
        PublicModelProfile(
            id=profile.id,
            provider=profile.provider,
            base_url=profile.base_url,
            model=profile.model,
            timeout_seconds=profile.timeout_seconds,
            available=not profile.api_key_env or bool(os.getenv(profile.api_key_env)),
        )
        for profile in get_settings().model_profiles
    ]
