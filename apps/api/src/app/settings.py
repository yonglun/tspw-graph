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
    api_version: str = "2024-06-01"
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
    auth_bootstrap_username: str = "admin"
    auth_bootstrap_password: str = "Pass@word1"
    auth_cookie_name: str = "tspw_admin_session"
    auth_cookie_secure: bool = False
    auth_session_idle_seconds: int = 8 * 60 * 60
    auth_login_max_failures: int = 5
    auth_login_lock_seconds: int = 15 * 60
    auth_trust_forwarded_ip: bool = False
    qa_model_profile_id: str = "azure:gpt-4o-mini"
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
