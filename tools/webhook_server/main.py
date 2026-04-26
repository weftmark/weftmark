"""Gitea webhook receiver for weaving_site dev tooling.

Start with:
    uvicorn main:app --port 3001 --reload
"""

import hashlib
import hmac
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request

from config import settings
from handlers import issue_comment

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
log = logging.getLogger(__name__)

HANDLERS = {
    "issue_comment": issue_comment.handle,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Webhook server ready on port %d  repo=%s  claude=%s", settings.port, settings.repo_path, settings.claude_bin)
    yield


app = FastAPI(title="weaving_site webhook server", lifespan=lifespan)


def _verify_signature(body: bytes, signature: str) -> None:
    """Raise 403 if the Gitea HMAC-SHA256 signature doesn't match."""
    expected = hmac.new(
        settings.webhook_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")


@app.post("/webhook")
async def webhook(
    request: Request,
    x_gitea_event: str = Header(..., alias="X-Gitea-Event"),
    x_gitea_signature: str = Header(..., alias="X-Gitea-Signature"),
):
    body = await request.body()
    _verify_signature(body, x_gitea_signature)

    payload = await request.json()
    log.info("received event: %s", x_gitea_event)

    handler = HANDLERS.get(x_gitea_event)
    if handler is None:
        log.info("no handler for event type %s", x_gitea_event)
        return {"status": "ignored", "event": x_gitea_event}

    try:
        await handler(payload)
    except Exception as exc:
        log.exception("handler %s raised: %s", x_gitea_event, exc)
        raise HTTPException(status_code=500, detail=str(exc))

    return {"status": "ok", "event": x_gitea_event}


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=True)
