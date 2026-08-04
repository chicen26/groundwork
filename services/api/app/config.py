"""Application configuration.

Every deployment knob is an environment variable; nothing secret is ever committed. See
`.env.example` for the full list.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="GROUNDWORK_", extra="ignore")

    # Service identity
    environment: str = "development"
    version: str = "0.1.0"

    # Rulebooks are data, not code: the active version is pinned per environment so a Zone 0
    # finalization ships as a content update rather than a deploy of new logic.
    rulebook_version: str = "unreleased"

    # Comma-separated origins allowed to call the API. Expo dev clients use exp:// and
    # http://localhost, so development stays permissive and production is explicit.
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Settings are read once per process; tests clear the cache when they override env vars."""
    return Settings()
