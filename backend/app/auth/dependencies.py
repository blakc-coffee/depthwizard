"""Supabase JWT verification dependency.

Owner: Backend Engineer A. See PRD §9.

Verifies the token signature, expiry, and audience; extracts identity from
`sub` only. A user_id supplied by the client (query param, body, header) is
never trusted — this is the one place identity is allowed to come from
(PRD §6/§9.2).

Assumes HS256 shared-secret signing (`SUPABASE_JWT_SECRET`), the common
default for Supabase projects. If this project uses the newer asymmetric
signing keys instead, swap the `jwt.decode(..., settings.supabase_jwt_secret,
algorithms=["HS256"])` call below for a JWKS fetch — this is the only place
that needs to change.
"""

from __future__ import annotations

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import get_settings
from app.core.errors import ApiException, ErrorCode

_bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    if credentials is None:
        raise ApiException(ErrorCode.AUTH_REQUIRED, "Missing bearer token.")

    settings = get_settings()
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.supabase_jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError as exc:
        raise ApiException(ErrorCode.INVALID_TOKEN, "Invalid or expired token.") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise ApiException(ErrorCode.INVALID_TOKEN, "Token has no subject claim.")

    return user_id
