"""Frontend log relay — accepts structured log events from the browser and
writes them through the shared JsonFormatter logger so client-side events
appear in the same JSON log stream as backend events.

Rate limiting is handled at the nginx layer (dedicated client_logs zone: 2 req/s).
Unauthenticated requests are silently dropped (204 with no logging) to prevent
log injection from external callers while never breaking client-side logging UX.
"""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.deps import get_optional_user
from app.models.user import User

log = logging.getLogger("frontend")
router = APIRouter(prefix="/api/logs", tags=["logs"])

_MAX_EVENTS_PER_REQUEST = 50


class ClientLogEvent(BaseModel):
    level: Literal["debug", "info", "warning", "error"]
    message: str = Field(max_length=2000)
    context: dict | None = None


@router.post("", status_code=204)
async def ingest_client_logs(
    events: Annotated[list[ClientLogEvent], Field(max_length=_MAX_EVENTS_PER_REQUEST)],
    request: Request,
    current_user: User | None = Depends(get_optional_user),
) -> None:
    if current_user is None:
        return
    client_ip = request.headers.get("X-Real-IP") or (request.client.host if request.client else "unknown")
    for event in events[:_MAX_EVENTS_PER_REQUEST]:
        level_fn = getattr(log, event.level, log.info)
        extra: dict = {"source": "browser", "client_ip": client_ip}
        if event.context:
            extra.update(event.context)
        level_fn(event.message, extra=extra)
