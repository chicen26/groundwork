"""Who is calling.

Supabase issues the tokens; we verify them ourselves rather than calling Supabase on every request
(governing principle 3, and it keeps auth working when their API is slow). Tokens are HS256, signed
with the project's JWT secret, and the subject claim is the user id our foreign keys point at.

Development has an escape hatch — an `X-Groundwork-User` header — because building the scan flow
should not require a Supabase project. It is refused outright when a JWT secret is configured or
when the environment is production, so it cannot survive into a deployment by accident.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, status

from app.config import Settings, get_settings

DEV_USER_HEADER = "X-Groundwork-User"

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="authentication required",
    headers={"WWW-Authenticate": "Bearer"},
)


def _user_id_from_token(token: str, settings: Settings) -> UUID:
    try:
        claims = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience=settings.supabase_jwt_audience or None,
            # Supabase tokens are short-lived; an expired one must be refused, not tolerated.
            options={"require": ["exp", "sub"]},
        )
    except jwt.InvalidTokenError as exc:
        raise _UNAUTHENTICATED from exc

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
        if not settings.supabase_jwt_secret:
            # Verifying with no secret would mean accepting any token. Fail closed.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="authentication is not configured on this server",
            )
        return _user_id_from_token(authorization.split(" ", 1)[1].strip(), settings)

    if x_groundwork_user:
        if settings.is_production or settings.supabase_jwt_secret:
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
