from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), interest-cohort=(), payment=(), usb=()"

# Clerk requires its own origins for script/frame/connect.
_CSP_PRODUCTION = (
    "default-src 'self'; "
    "script-src 'self' https://clerk.com https://*.clerk.accounts.dev https://*.clerk.com; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob: https://*.clerk.com; "
    "connect-src 'self' https://clerk.com https://*.clerk.accounts.dev https://*.clerk.com; "
    "frame-src https://clerk.com https://*.clerk.accounts.dev https://*.clerk.com; "
    "font-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, production: bool = False) -> None:
        super().__init__(app)
        self._production = production

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = _PERMISSIONS_POLICY
        if self._production:
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
            response.headers["Content-Security-Policy"] = _CSP_PRODUCTION
        return response
