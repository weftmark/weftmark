"""Per-IP Redis-backed rate limiting — returned as FastAPI Depends() factories.

Usage:
    _my_limit = rate_limit("my_endpoint", max_requests=20, window_seconds=3600)

    @router.post("/endpoint")
    async def my_endpoint(..., _rl: None = Depends(_my_limit)):
        ...

Keys stored in Redis as  rl:<prefix>:<ip>  with a TTL equal to window_seconds.
The window is fixed (not sliding): the counter resets after window_seconds from
the first request in that window.
"""

import redis.asyncio as aioredis
from fastapi import HTTPException, Request

from app.config import get_settings

settings = get_settings()


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit(key_prefix: str, max_requests: int, window_seconds: int):
    """Return a FastAPI dependency that enforces a per-IP rate limit via Redis."""

    async def _check(request: Request) -> None:
        ip = _get_client_ip(request)
        key = f"rl:{key_prefix}:{ip}"
        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        try:
            count = await client.incr(key)
            # nx=True: only set TTL on the first increment (fixes the window start)
            await client.expire(key, window_seconds, nx=True)
            if count > max_requests:
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests. Please try again later.",
                    headers={"Retry-After": str(window_seconds)},
                )
        finally:
            await client.aclose()

    return _check
