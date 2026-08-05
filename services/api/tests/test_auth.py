"""Authentication tests.

Tokens are verified against Supabase's public JWKS, so these tests mint a real ES256 keypair, serve
it as a JWKS, and sign tokens with it. Testing against the real algorithm is the point: the failure
modes that matter here — a wrong key, an expired token, a forged `alg` — are all algorithm-specific,
and a stubbed verifier would prove none of them.

The rest is about the development header never becoming a production hole.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException

from app import auth
from app.auth import current_user_id
from app.config import Settings

ISSUER = "https://project.supabase.co/auth/v1"
JWKS_URL = "https://project.supabase.co/auth/v1/.well-known/jwks.json"
KID = "test-key-1"


@pytest.fixture
def keypair():
    return ec.generate_private_key(ec.SECP256R1())


class FakeJWKSClient:
    """Stands in for the network fetch, returning a key we control."""

    def __init__(self, key) -> None:
        self._key = key

    def get_signing_key_from_jwt(self, token: str):
        return type("Key", (), {"key": self._key})()


@pytest.fixture
def configured(monkeypatch, keypair):
    """Auth configured, with the JWKS fetch replaced by our own key."""
    monkeypatch.setattr(auth, "_jwks_client", lambda url: FakeJWKSClient(keypair.public_key()))
    return Settings(environment="development", supabase_url="https://project.supabase.co")


def make_token(
    key,
    *,
    sub: str,
    expires_in_s: int = 3600,
    audience: str = "authenticated",
    issuer: str = ISSUER,
) -> str:
    claims = {
        "sub": sub,
        "exp": datetime.now(UTC) + timedelta(seconds=expires_in_s),
        "aud": audience,
        "iss": issuer,
    }
    return jwt.encode(claims, key, algorithm="ES256", headers={"kid": KID})


# --------------------------------------------------------------------------- real tokens


async def test_a_valid_token_yields_its_subject(configured, keypair) -> None:
    user_id = uuid4()
    token = make_token(keypair, sub=str(user_id))

    assert await current_user_id(configured, authorization=f"Bearer {token}") == user_id


async def test_an_expired_token_is_refused(configured, keypair) -> None:
    token = make_token(keypair, sub=str(uuid4()), expires_in_s=-60)

    with pytest.raises(HTTPException) as exc:
        await current_user_id(configured, authorization=f"Bearer {token}")
    assert exc.value.status_code == 401


async def test_a_token_signed_by_a_different_key_is_refused(configured) -> None:
    """The core guarantee: only Supabase's key produces a token we accept."""
    attacker_key = ec.generate_private_key(ec.SECP256R1())
    token = make_token(attacker_key, sub=str(uuid4()))

    with pytest.raises(HTTPException) as exc:
        await current_user_id(configured, authorization=f"Bearer {token}")
    assert exc.value.status_code == 401


async def test_a_token_for_another_audience_is_refused(configured, keypair) -> None:
    token = make_token(keypair, sub=str(uuid4()), audience="some-other-service")

    with pytest.raises(HTTPException) as exc:
        await current_user_id(configured, authorization=f"Bearer {token}")
    assert exc.value.status_code == 401


async def test_a_token_from_another_issuer_is_refused(configured, keypair) -> None:
    """A token minted by a different Supabase project must not open this one."""
    token = make_token(keypair, sub=str(uuid4()), issuer="https://someone-else.supabase.co/auth/v1")

    with pytest.raises(HTTPException) as exc:
        await current_user_id(configured, authorization=f"Bearer {token}")
    assert exc.value.status_code == 401


async def test_a_token_with_a_non_uuid_subject_is_refused(configured, keypair) -> None:
    token = make_token(keypair, sub="not-a-uuid")

    with pytest.raises(HTTPException) as exc:
        await current_user_id(configured, authorization=f"Bearer {token}")
    assert exc.value.status_code == 401


async def test_an_unsigned_token_is_refused(configured) -> None:
    """`alg: none` is the oldest JWT attack there is; the algorithm allowlist is what stops it."""
    token = jwt.encode(
        {"sub": str(uuid4()), "exp": datetime.now(UTC) + timedelta(hours=1)},
        key="",
        algorithm="none",
    )

    with pytest.raises(HTTPException) as exc:
        await current_user_id(configured, authorization=f"Bearer {token}")
    assert exc.value.status_code == 401


async def test_a_jwks_outage_is_reported_as_ours_not_as_a_bad_token(monkeypatch, keypair) -> None:
    """503, not 401. Telling a user their credentials are wrong when our fetch failed is a lie."""

    class BrokenClient:
        def get_signing_key_from_jwt(self, token: str):
            raise ConnectionError("jwks unreachable")

    monkeypatch.setattr(auth, "_jwks_client", lambda url: BrokenClient())
    settings = Settings(environment="development", supabase_url="https://project.supabase.co")
    token = make_token(keypair, sub=str(uuid4()))

    with pytest.raises(HTTPException) as exc:
        await current_user_id(settings, authorization=f"Bearer {token}")
    assert exc.value.status_code == 503


# --------------------------------------------------------------------------- the dev header


async def test_a_bearer_token_with_no_auth_configured_is_refused_not_trusted() -> None:
    """With no key source we cannot verify anything, so we must fail closed rather than accept."""
    settings = Settings(environment="development")
    token = jwt.encode({"sub": str(uuid4())}, "anything", algorithm="HS256")

    with pytest.raises(HTTPException) as exc:
        await current_user_id(settings, authorization=f"Bearer {token}")
    assert exc.value.status_code == 503


async def test_the_dev_header_works_before_auth_is_configured() -> None:
    user_id = uuid4()
    settings = Settings(environment="development")

    assert await current_user_id(settings, x_groundwork_user=str(user_id)) == user_id


async def test_the_dev_header_is_refused_in_production() -> None:
    settings = Settings(environment="production")

    with pytest.raises(HTTPException) as exc:
        await current_user_id(settings, x_groundwork_user=str(uuid4()))
    assert exc.value.status_code == 401


async def test_the_dev_header_is_refused_once_supabase_is_configured(configured) -> None:
    """Even in development: the moment real tokens can be verified, the shortcut closes."""
    with pytest.raises(HTTPException) as exc:
        await current_user_id(configured, x_groundwork_user=str(uuid4()))
    assert exc.value.status_code == 401


async def test_a_malformed_dev_header_is_a_bad_request() -> None:
    settings = Settings(environment="development")

    with pytest.raises(HTTPException) as exc:
        await current_user_id(settings, x_groundwork_user="not-a-uuid")
    assert exc.value.status_code == 400


async def test_no_credentials_at_all_is_unauthenticated() -> None:
    with pytest.raises(HTTPException) as exc:
        await current_user_id(Settings(environment="development"))
    assert exc.value.status_code == 401


# --------------------------------------------------------------------------- configuration


def test_the_jwks_and_issuer_urls_are_derived_from_the_project_url() -> None:
    """One URL to configure, not three that have to agree."""
    settings = Settings(supabase_url="https://project.supabase.co/")

    assert settings.supabase_jwks_url == JWKS_URL
    assert settings.supabase_issuer == ISSUER
    assert settings.auth_configured


def test_no_secret_is_ever_read_from_configuration() -> None:
    """The whole point of JWKS here: there is no shared secret to leak from this service."""
    fields = set(Settings.model_fields)

    assert not [f for f in fields if "secret" in f]


def test_auth_is_not_configured_without_a_project_url() -> None:
    assert not Settings().auth_configured


def test_the_algorithm_allowlist_excludes_symmetric_and_none() -> None:
    """HS256 with the public key as the secret is a real forgery path if `alg` is unconstrained."""
    assert "none" not in auth.ALLOWED_ALGORITHMS
    assert not [a for a in auth.ALLOWED_ALGORITHMS if a.startswith("HS")]


def test_the_real_supabase_jwks_shape_is_what_we_expect() -> None:
    """Recorded from the live project on Aug 5, 2026, so a format change fails here first."""
    recorded = json.loads(
        '{"keys":[{"alg":"ES256","crv":"P-256","kid":"302f45f4-e936-40bd-b4a7-54c521656802",'
        '"kty":"EC","use":"sig","x":"eT2lLA3h58hL_JKOBLn8517FjT3x4zyfsvLr45OY9Hs",'
        '"y":"NcXRyu9YYlxAbvhc_x1UMUgus18Jtab3mY6Ge9zlvxw"}]}'
    )

    key = recorded["keys"][0]
    assert key["alg"] in auth.ALLOWED_ALGORITHMS
    assert key["use"] == "sig"
    # Public coordinates only — nothing in a JWKS is a secret.
    assert "d" not in key
