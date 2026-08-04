"""Authentication tests.

The development header is a convenience that must never become a production hole, so most of these
tests are about the ways it is refused.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from fastapi import HTTPException

from app.auth import current_user_id
from app.config import Settings

# Long enough to satisfy RFC 7518 for HS256; short keys make PyJWT warn, and a test suite that
# warns on every run trains people to ignore warnings.
TEST_SECRET = "groundwork-test-secret-value-0123456789"
OTHER_SECRET = "a-different-secret-value-0123456789abcd"


def settings_for(**overrides: object) -> Settings:
    return Settings(environment="development", **overrides)  # type: ignore[arg-type]


def make_token(secret: str, *, sub: str, expires_in_s: int = 3600, audience: str | None = None):
    claims = {
        "sub": sub,
        "exp": datetime.now(UTC) + timedelta(seconds=expires_in_s),
        "aud": audience or "authenticated",
    }
    return jwt.encode(claims, secret, algorithm="HS256")


async def test_valid_token_yields_its_subject() -> None:
    user_id = uuid4()
    settings = settings_for(supabase_jwt_secret=TEST_SECRET)
    token = make_token(TEST_SECRET, sub=str(user_id))

    assert await current_user_id(settings, authorization=f"Bearer {token}") == user_id


async def test_expired_token_is_refused() -> None:
    settings = settings_for(supabase_jwt_secret=TEST_SECRET)
    token = make_token(TEST_SECRET, sub=str(uuid4()), expires_in_s=-60)

    with pytest.raises(HTTPException) as exc:
        await current_user_id(settings, authorization=f"Bearer {token}")
    assert exc.value.status_code == 401


async def test_token_signed_with_the_wrong_secret_is_refused() -> None:
    settings = settings_for(supabase_jwt_secret=TEST_SECRET)
    token = make_token(OTHER_SECRET, sub=str(uuid4()))

    with pytest.raises(HTTPException) as exc:
        await current_user_id(settings, authorization=f"Bearer {token}")
    assert exc.value.status_code == 401


async def test_bearer_token_without_a_configured_secret_is_refused_not_trusted() -> None:
    """With no secret we cannot verify anything, so we must fail closed rather than accept."""
    settings = settings_for(supabase_jwt_secret="")
    token = make_token(OTHER_SECRET, sub=str(uuid4()))

    with pytest.raises(HTTPException) as exc:
        await current_user_id(settings, authorization=f"Bearer {token}")
    assert exc.value.status_code == 503


async def test_dev_header_works_only_in_development() -> None:
    user_id = uuid4()
    settings = settings_for()

    assert await current_user_id(settings, x_groundwork_user=str(user_id)) == user_id


async def test_dev_header_is_refused_in_production() -> None:
    settings = Settings(environment="production")

    with pytest.raises(HTTPException) as exc:
        await current_user_id(settings, x_groundwork_user=str(uuid4()))
    assert exc.value.status_code == 401


async def test_dev_header_is_refused_once_real_auth_is_configured() -> None:
    """Even in development: if tokens can be verified, the shortcut is off."""
    settings = settings_for(supabase_jwt_secret=TEST_SECRET)

    with pytest.raises(HTTPException) as exc:
        await current_user_id(settings, x_groundwork_user=str(uuid4()))
    assert exc.value.status_code == 401


async def test_no_credentials_at_all_is_unauthenticated() -> None:
    with pytest.raises(HTTPException) as exc:
        await current_user_id(settings_for())
    assert exc.value.status_code == 401
