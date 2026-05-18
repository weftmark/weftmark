"""Dedicated webhook ingress — replaces /auth/clerk/webhook.

POST /webhooks/clerk  — Clerk user lifecycle events (user.created, user.updated,
                        user.deleted, session.created, session.ended, webhook.test)

Migration: during the Clerk dual-registration window both /auth/clerk/webhook and
/webhooks/clerk are active. Once delivery on /webhooks/clerk is confirmed in the
Clerk dashboard, decommission /auth/clerk/webhook in a follow-up PR.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.routers.auth import _handle_clerk_webhook

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/clerk", status_code=200)
async def clerk_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """Receive and process Clerk user lifecycle events."""
    return await _handle_clerk_webhook(request, db)
