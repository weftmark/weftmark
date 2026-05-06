"""Unit tests for the Redis-backed rate limiter."""

from unittest.mock import patch

import fakeredis.aioredis
import pytest
from fastapi import HTTPException
from starlette.requests import Request


def _make_request(ip: str = "1.2.3.4", forwarded_for: str | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/test",
        "headers": [],
        "client": (ip, 12345),
    }
    if forwarded_for:
        scope["headers"] = [(b"x-forwarded-for", forwarded_for.encode())]
    return Request(scope)


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


class TestRateLimiter:
    async def test_allows_requests_under_limit(self, fake_redis):
        from app.services.rate_limiter import rate_limit

        limiter = rate_limit("test", max_requests=5, window_seconds=60)
        request = _make_request()

        with patch("app.services.rate_limiter.aioredis.from_url", return_value=fake_redis):
            for _ in range(5):
                await limiter(request)  # should not raise

    async def test_blocks_request_over_limit(self, fake_redis):
        from app.services.rate_limiter import rate_limit

        limiter = rate_limit("test_block", max_requests=3, window_seconds=60)
        request = _make_request()

        with patch("app.services.rate_limiter.aioredis.from_url", return_value=fake_redis):
            for _ in range(3):
                await limiter(request)
            with pytest.raises(HTTPException) as exc_info:
                await limiter(request)
        assert exc_info.value.status_code == 429

    async def test_429_includes_retry_after_header(self, fake_redis):
        from app.services.rate_limiter import rate_limit

        limiter = rate_limit("test_header", max_requests=1, window_seconds=300)
        request = _make_request()

        with patch("app.services.rate_limiter.aioredis.from_url", return_value=fake_redis):
            await limiter(request)
            with pytest.raises(HTTPException) as exc_info:
                await limiter(request)
        assert "Retry-After" in exc_info.value.headers
        assert exc_info.value.headers["Retry-After"] == "300"

    async def test_different_ips_have_independent_counters(self, fake_redis):
        from app.services.rate_limiter import rate_limit

        limiter = rate_limit("test_ip", max_requests=1, window_seconds=60)
        req_a = _make_request(ip="10.0.0.1")
        req_b = _make_request(ip="10.0.0.2")

        with patch("app.services.rate_limiter.aioredis.from_url", return_value=fake_redis):
            await limiter(req_a)  # first request from A — OK
            await limiter(req_b)  # first request from B — OK (independent counter)

    async def test_uses_x_forwarded_for_when_present(self, fake_redis):
        from app.services.rate_limiter import rate_limit

        limiter = rate_limit("test_xff", max_requests=1, window_seconds=60)
        # Socket IP is proxy; real client IP is in X-Forwarded-For
        req = _make_request(ip="172.18.0.1", forwarded_for="203.0.113.5, 172.18.0.1")

        with patch("app.services.rate_limiter.aioredis.from_url", return_value=fake_redis):
            await limiter(req)  # OK
            with pytest.raises(HTTPException):
                await limiter(req)  # 429 — counted against 203.0.113.5, not proxy IP


class TestGetClientIp:
    def test_returns_socket_ip_when_no_header(self):
        from app.services.rate_limiter import _get_client_ip

        req = _make_request(ip="9.8.7.6")
        assert _get_client_ip(req) == "9.8.7.6"

    def test_returns_first_forwarded_for_ip(self):
        from app.services.rate_limiter import _get_client_ip

        req = _make_request(forwarded_for="1.1.1.1, 2.2.2.2, 3.3.3.3")
        assert _get_client_ip(req) == "1.1.1.1"

    def test_strips_whitespace_from_forwarded_for(self):
        from app.services.rate_limiter import _get_client_ip

        req = _make_request(forwarded_for="  1.1.1.1  , 2.2.2.2")
        assert _get_client_ip(req) == "1.1.1.1"
