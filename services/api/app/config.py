"""Application configuration.

Every deployment knob is an environment variable; nothing secret is ever committed. See
`.env.example` for the full list.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
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

    # Supabase issues the JWTs. We verify them against the project's **public** JWKS, so no shared
    # secret ever lives in this service — nothing that could leak from our side would let anyone
    # forge a token. While this is empty the API accepts the development user header instead; see
    # app/auth.py, which refuses that fallback in production.
    supabase_url: str = ""
    supabase_jwks_url: str = ""
    supabase_jwt_audience: str = "authenticated"
    supabase_issuer: str = ""

    # Where sanitised photographs are written. Local filesystem today; the storage interface in
    # app/storage.py is small enough that a Supabase Storage backend drops in without touching a
    # handler.
    photo_storage_root: str = "./var/photos"

    # Path to the fine-tuned detector weights. Empty means no model is configured: inference
    # jobs then fail honestly rather than reporting a clean yard nobody earned, which is what
    # app/inference/detector.py's NullDetector exists to guarantee.
    detector_weights: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def auth_configured(self) -> bool:
        """True once we can actually verify a token, which is what closes the dev-header door."""
        return bool(self.supabase_jwks_url)

    @model_validator(mode="after")
    def derive_supabase_urls(self) -> Settings:
        """Fill in the JWKS and issuer URLs from the project URL.

        Supabase publishes both at fixed paths, so asking a deployer for three URLs that must agree
        is three chances to get it wrong. Either is still overridable when a setup differs.
        """
        if self.supabase_url:
            base = self.supabase_url.rstrip("/")
            if not self.supabase_jwks_url:
                self.supabase_jwks_url = f"{base}/auth/v1/.well-known/jwks.json"
            if not self.supabase_issuer:
                self.supabase_issuer = f"{base}/auth/v1"
        return self


@lru_cache
def get_settings() -> Settings:
    """Settings are read once per process; tests clear the cache when they override env vars."""
    return Settings()
