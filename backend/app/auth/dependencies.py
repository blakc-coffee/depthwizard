"""Supabase JWT verification dependency.

Owner: Backend Engineer A. See PRD §9.

Verifies the token signature, expiry, and audience; extracts identity from
`sub` only. A user_id supplied by the client (query param, body, header) is
never trusted — this is the one place identity is allowed to come from
(PRD §6/§9.2).

Verifies against Supabase's published JWKS (asymmetric signing keys — this
project's current signing key is ECC/P-256, i.e. ES256; the older shared
HS256 secret is being phased out, see Supabase dashboard -> JWT Keys).
`PyJWKClient` resolves the right public key by the token's `kid` header and
caches the fetched key set, so this also transparently covers key rotation:
both the CURRENT key and any not-yet-revoked PREVIOUS key are served from
the same JWKS endpoint. No shared secret is configured here at all — that's
the point of asymmetric verification.
"""

from __future__ import annotations

import threading
import time
from functools import lru_cache

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWK, PyJWKClient

from app.core.config import get_settings
from app.core.errors import ApiException, ErrorCode

_bearer_scheme = HTTPBearer(auto_error=False)

# PyJWKClient refetches the JWKS whenever a token names an unknown `kid`, so
# any forged token could force an outbound call to Supabase. Allow that
# refetch at most once per cooldown; a real key rotation is still picked up.
_UNKNOWN_KID_REFRESH_COOLDOWN_SECONDS = 60
_last_unknown_kid_refresh = float("-inf")
_refresh_lock = threading.Lock()


@lru_cache
def _get_jwks_client() -> PyJWKClient:
    jwks_url = f"{get_settings().supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"
    return PyJWKClient(jwks_url, timeout=5)


def _get_signing_key(token: str) -> PyJWK:
    global _last_unknown_kid_refresh
    client = _get_jwks_client()
    kid = jwt.get_unverified_header(token).get("kid")
    if not kid:
        raise jwt.InvalidTokenError("Token has no kid header.")

    key = client.match_kid(client.get_signing_keys(), kid)
    if key is None:
        with _refresh_lock:
            # Another thread may have refreshed while this one waited.
            key = client.match_kid(client.get_signing_keys(), kid)
            now = time.monotonic()
            if key is None and now - _last_unknown_kid_refresh >= _UNKNOWN_KID_REFRESH_COOLDOWN_SECONDS:
                _last_unknown_kid_refresh = now
                key = client.match_kid(client.get_signing_keys(refresh=True), kid)
    if key is None:
        raise jwt.InvalidTokenError("Unknown signing key.")
    return key


def get_current_user_id(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    if credentials is None:
        raise ApiException(ErrorCode.AUTH_REQUIRED, "Missing bearer token.")

    try:
        signing_key = _get_signing_key(credentials.credentials)
        payload = jwt.decode(
            credentials.credentials,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
        )
    except jwt.PyJWTError as exc:
        raise ApiException(ErrorCode.INVALID_TOKEN, "Invalid or expired token.") from exc

    user_id = payload.get("sub")
    if not user_id:
        raise ApiException(ErrorCode.INVALID_TOKEN, "Token has no subject claim.")

    # Lets core/rate_limit.py key throttling by user instead of IP —
    # ownership/isolation itself never depends on this, only rate limiting does.
    request.state.user_id = user_id
    return user_id
