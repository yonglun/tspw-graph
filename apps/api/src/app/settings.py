from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelProfileSettings(BaseModel):
    id: str
    provider: str
    base_url: str = ""
    model: str
    api_key_env: str = ""
    timeout_seconds: float = 60


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", populate_by_name=True
    )

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "development-only"
    sqlite_url: str = "sqlite:///./tspw-graph.db"
    data_root: Path = Path("./data/uploads")
    max_upload_bytes: int = 20 * 1024 * 1024
    model_profiles: list[ModelProfileSettings] = Field(
        default_factory=lambda: [
            ModelProfileSettings(
                id="fixed:test", provider="fixed", model="deterministic-test"
            )
        ],
        validation_alias="MODEL_PROFILES_JSON",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
