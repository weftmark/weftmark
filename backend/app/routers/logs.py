"""Frontend log relay — accepts structured log events from the browser and
writes them through the shared JsonFormatter logger so client-side events
appear in the same JSON log stream as backend events.

Rate limiting is handled at the nginx layer (30 req/s per IP on /api/).
No authentication required — this endpoint only writes, never reads.
"""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

log = logging.getLogger("frontend")
router = APIRouter(tags=["logs"])

_MAX_EVENTS_PER_REQUEST = 50


class ClientLogEvent(BaseModel):
    level: Literal["debug", "info", "warning", "error"]
    message: str = Field(max_length=2000)
    context: dict | None = None


@router.post("/api/logs", status_code=204)
async def ingest_client_logs(
    events: Annotated[list[ClientLogEvent], Field(max_length=_MAX_EVENTS_PER_REQUEST)],
    request: Request,
) -> None:
    client_ip = request.headers.get("X-Real-IP") or (request.client.host if request.client else "unknown")
    for event in events[:_MAX_EVENTS_PER_REQUEST]:
        level_fn = getattr(log, event.level, log.info)
        extra: dict = {"source": "browser", "client_ip": client_ip}
        if event.context:
            extra.update(event.context)
        level_fn(event.message, extra=extra)
