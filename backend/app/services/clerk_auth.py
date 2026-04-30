"""Clerk JWT verification and webhook helpers."""

import base64
import logging

import jwt
from jwt import PyJWKClient

log = logging.getLogger(__name__)

# PyJWKClient caches keys and refreshes on unknown kid automatically.
_jwks_clients: dict[str, PyJWKClient] = {}


def jwks_url_from_publishable_key(pk: str) -> str:
    """Derive JWKS URL from a Clerk publishable key (pk_test_... / pk_live_...)."""
    parts = pk.split("_")
    if len(parts) < 3:
        raise ValueError(f"Invalid Clerk publishable key: {pk!r}")
    encoded = parts[2]
    padded = encoded + "=" * (4 - len(encoded) % 4)
    domain = base64.urlsafe_b64decode(padded).decode("utf-8").rstrip("$")
    return f"https://{domain}/.well-known/jwks.json"


def _jwks_client(jwks_url: str) -> PyJWKClient:
    if jwks_url not in _jwks_clients:
        _jwks_clients[jwks_url] = PyJWKClient(jwks_url, cache_keys=True)
    return _jwks_clients[jwks_url]


def verify_session_token(token: str, jwks_url: str) -> str | None:
    """Verify a Clerk session token. Returns the clerk_user_id (sub) or None."""
    try:
        client = _jwks_client(jwks_url)
        signing_key = client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        return payload.get("sub")
    except Exception as exc:
        log.info("jwt_verification_failed type=%s detail=%s", type(exc).__name__, exc)
        return None
