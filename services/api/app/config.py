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
    rulebook_version: str = "2026.08"

    # Comma-separated origins allowed to call the API. Expo dev clients use exp:// and
    # http://localhost, so development stays permissive and production is explicit.
    cors_origins: str = "*"

    # Postgres/PostGIS connection string. Empty in unit-test runs that never touch the database;
    # startup fails loudly if it is missing in production.
    database_url: str = ""
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10

    # Supabase issues the JWTs; we verify them locally with this secret. When it is empty the API
    # accepts the development user header instead — see app/auth.py, which refuses that fallback in
    # production.
    supabase_jwt_secret: str = ""
    supabase_jwt_audience: str = "authenticated"

    # Where sanitised photographs are written. Local filesystem today; the storage interface in
    # app/storage.py is small enough that a Supabase Storage backend drops in without touching a
    # handler.
    photo_storage_root: str = "./var/photos"

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
