"""Webhook ingress.

POST /webhooks/clerk  — Clerk user lifecycle events (user.created, user.updated,
                        user.deleted, session.created, session.ended, webhook.test)
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.routers.auth import _handle_clerk_webhook

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post(
    "/clerk",
    status_code=200,
    responses={
        400: {"description": "Invalid webhook signature"},
        500: {"description": "Webhook not configured"},
    },
)
async def clerk_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """Receive and process Clerk user lifecycle events."""
    return await _handle_clerk_webhook(request, db)
