"""Webhook round-trip probe.

Signs a synthetic test event with the webhook secret and POSTs it to the
configured public webhook URL.  The webhook handler recognises the event type
and signals an asyncio.Event so the probe can measure end-to-end latency.

Skipped gracefully when WEBHOOK_BASE_URL or CLERK_WEBHOOK_SECRET is unset
(e.g. local dev without a tunnel).  A timeout is a soft failure — it sets
degraded state, not an error, so the app still starts and serves users.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Literal

import httpx
from svix.webhooks import Webhook

from app.config import get_settings

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared state — one probe runs at a time
# ---------------------------------------------------------------------------

_probe_lock: asyncio.Lock | None = None
_pending_event: asyncio.Event | None = None


def _get_lock() -> asyncio.Lock:
    global _probe_lock
    if _probe_lock is None:
        _probe_lock = asyncio.Lock()
    return _probe_lock


def signal_probe() -> None:
    """Called by the webhook handler when a webhook.test event is received."""
    global _pending_event
    if _pending_event is not None:
        _pending_event.set()


# ---------------------------------------------------------------------------
# Probe result
# ---------------------------------------------------------------------------


class WebhookProbeResult:
    def __init__(
        self,
        status: Literal["ok", "skipped", "error"],
        latency_ms: int | None = None,
        message: str = "",
    ) -> None:
        self.status = status
        self.latency_ms = latency_ms
        self.message = message


# ---------------------------------------------------------------------------
# Core probe logic
# ---------------------------------------------------------------------------


async def run_webhook_probe() -> WebhookProbeResult:
    """Run the webhook round-trip probe and return the result."""
    settings = get_settings()

    if not settings.clerk_webhook_secret:
        return WebhookProbeResult("error", message="CLERK_WEBHOOK_SECRET not configured")

    base = (settings.webhook_base_url or settings.api_url).rstrip("/")
    webhook_url = base + "/auth/clerk/webhook"
    timeout = settings.clerk_webhook_probe_timeout_s

    global _pending_event
    lock = _get_lock()

    try:
        await asyncio.wait_for(lock.acquire(), timeout=5.0)
    except asyncio.TimeoutError:
        return WebhookProbeResult("error", message="Another probe is already running")

    try:
        _pending_event = asyncio.Event()

        msg_id = f"msg_{uuid.uuid4().hex}"
        ts = datetime.now(timezone.utc)
        payload_str = json.dumps({"type": "webhook.test", "data": {"probe_id": msg_id}})
        payload_bytes = payload_str.encode()

        wh = Webhook(settings.clerk_webhook_secret)
        signature = wh.sign(msg_id, ts, payload_str)

        headers = {
            "Content-Type": "application/json",
            "svix-id": msg_id,
            "svix-timestamp": str(int(ts.timestamp())),
            "svix-signature": signature,
        }

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.post(webhook_url, content=payload_bytes, headers=headers)
            if r.status_code not in (200, 202, 204):
                return WebhookProbeResult("error", message=f"Webhook endpoint returned HTTP {r.status_code}")
        except httpx.TimeoutException:
            return WebhookProbeResult("error", message="HTTP POST to webhook endpoint timed out")
        except Exception as exc:
            return WebhookProbeResult("error", message=f"HTTP POST failed: {exc!s:.80}")

        try:
            await asyncio.wait_for(_pending_event.wait(), timeout=float(timeout))
        except asyncio.TimeoutError:
            return WebhookProbeResult(
                "error",
                message=f"Test event not received within {timeout}s — check Svix delivery or firewall",
            )

        latency_ms = int((time.monotonic() - start) * 1000)
        log.info("Webhook probe succeeded in %dms", latency_ms)
        return WebhookProbeResult("ok", latency_ms=latency_ms, message=f"Round-trip in {latency_ms}ms")

    finally:
        _pending_event = None
        lock.release()
