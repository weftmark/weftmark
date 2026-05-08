"""
Lightweight SMTP health check: bare TCP probe with a circuit-breaker backoff.

Replaces the full aiosmtplib auth session that previously ran every 30 s,
consuming a real SMTP2Go login slot each cycle.  A TCP connection verifies
reachability without triggering rate-limits or auth quotas.

Circuit-breaker behaviour:
- First failure → enters backoff; subsequent calls return cached failure for
  BACKOFF_SECONDS without opening another socket.
- First success after backoff → resets to normal; every call probes live.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

TCP_TIMEOUT_S: float = 5.0
BACKOFF_SECONDS: int = 300  # 5 minutes between retries after a failure

# Module-level circuit-breaker state (single asyncio event loop — no lock needed)
_last_ok: bool | None = None
_last_message: str = ""
_last_checked_at: datetime | None = None
_in_backoff: bool = False


async def _tcp_probe(host: str, port: int) -> tuple[bool, str]:
    """Open a bare TCP connection to host:port and immediately close it."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=TCP_TIMEOUT_S,
        )
        writer.close()
        await writer.wait_closed()
        return True, f"TCP connected to {host}:{port}"
    except asyncio.TimeoutError:
        return False, f"TCP connection timed out after {TCP_TIMEOUT_S:.0f} s"
    except OSError as exc:
        return False, str(exc)[:120]
    except Exception as exc:  # pragma: no cover
        return False, str(exc)[:120]


async def check(host: str, port: int) -> tuple[bool, str]:
    """Return ``(ok, message)`` for SMTP TCP reachability.

    After a failure the cached result is returned for BACKOFF_SECONDS to
    avoid hammering the relay.  A success resets the circuit immediately.
    """
    global _last_ok, _last_message, _last_checked_at, _in_backoff

    now = datetime.now(timezone.utc)

    if _in_backoff and _last_checked_at is not None:
        elapsed = (now - _last_checked_at).total_seconds()
        remaining = int(BACKOFF_SECONDS - elapsed)
        if remaining > 0:
            log.debug("smtp_health: backoff active, %ds remaining", remaining)
            return False, f"{_last_message} (cached — retry in {remaining}s)"

    ok, msg = await _tcp_probe(host, port)

    _last_ok = ok
    _last_message = msg
    _last_checked_at = now
    _in_backoff = not ok

    return ok, msg


def reset() -> None:
    """Reset circuit-breaker state. Intended for tests."""
    global _last_ok, _last_message, _last_checked_at, _in_backoff
    _last_ok = None
    _last_message = ""
    _last_checked_at = None
    _in_backoff = False
