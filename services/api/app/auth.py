"""Who is calling.

Supabase issues the tokens; we verify them ourselves rather than calling Supabase on every request
(governing principle 3, and it keeps auth working when their API is slow).

Verification uses Supabase's **public** JWKS — the project signs with ES256 and publishes the
verifying key, so this service never holds a shared secret at all. Nothing that could leak from our
side would let anyone forge a token. The key set is cached and only refetched when a token arrives
signed by a key id we have not seen, which is what makes key rotation a non-event.

Development still has an escape hatch — an `X-Groundwork-User` header — because building the scan
flow should not require a Supabase project. It is refused outright once auth is configured or when
the environment is production, so it cannot survive into a deployment by accident.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, status
from jwt import PyJWKClient

from app.config import Settings, get_settings

DEV_USER_HEADER = "X-Groundwork-User"

# Supabase signs with ES256. Listing algorithms explicitly is what stops an attacker presenting a
# token that claims `alg: none`, or an HMAC token signed with the public key.
ALLOWED_ALGORITHMS = ["ES256", "RS256"]

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="authentication required",
    headers={"WWW-Authenticate": "Bearer"},
)


@lru_cache
def _jwks_client(url: str) -> PyJWKClient:
    """One client per JWKS URL, caching keys in memory across requests."""
    return PyJWKClient(url, cache_keys=True, lifespan=3600)


def _user_id_from_token(token: str, settings: Settings) -> UUID:
    try:
        signing_key = _jwks_client(settings.supabase_jwks_url).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=ALLOWED_ALGORITHMS,
            audience=settings.supabase_jwt_audience or None,
            issuer=settings.supabase_issuer or None,
            # Supabase tokens are short-lived; an expired one must be refused, not tolerated.
            options={"require": ["exp", "sub"]},
        )
    except jwt.InvalidTokenError as exc:
        raise _UNAUTHENTICATED from exc
    except Exception as exc:
        # A JWKS fetch failure is ours, not the caller's, and must not read as "your token is bad".
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="could not verify credentials right now",
        ) from exc

    try:
        return UUID(claims["sub"])
    except (KeyError, ValueError) as exc:
        raise _UNAUTHENTICATED from exc


async def current_user_id(
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
    x_groundwork_user: Annotated[str | None, Header()] = None,
) -> UUID:
    """Resolve the caller's user id from a bearer token, or the dev header when permitted."""
    if authorization and authorization.lower().startswith("bearer "):
        if not settings.auth_configured:
            # Verifying with no key source would mean accepting anything. Fail closed.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="authentication is not configured on this server",
            )
        token = authorization.split(" ", 1)[1].strip()
        # Key fetches are blocking; keep one cold start off the event loop.
        return await asyncio.to_thread(_user_id_from_token, token, settings)

    if x_groundwork_user:
        if settings.is_production or settings.auth_configured:
            raise _UNAUTHENTICATED
        try:
            return UUID(x_groundwork_user)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{DEV_USER_HEADER} must be a UUID",
            ) from exc

    raise _UNAUTHENTICATED


CurrentUser = Annotated[UUID, Depends(current_user_id)]
