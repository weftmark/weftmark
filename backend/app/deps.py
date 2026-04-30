import logging
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.user import User
from app.services.clerk_auth import jwks_url_from_publishable_key, verify_session_token

log = logging.getLogger(__name__)

_LAST_ACTIVE_THROTTLE = timedelta(minutes=5)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    settings = get_settings()
    method = request.method
    path = request.url.path

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        log.info("auth_failure reason=no_token method=%s path=%s", method, path)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token = auth_header.removeprefix("Bearer ").strip()

    if not settings.clerk_publishable_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Auth not configured")

    jwks_url = jwks_url_from_publishable_key(settings.clerk_publishable_key)
    clerk_user_id = verify_session_token(token, jwks_url)
    if not clerk_user_id:
        log.info("auth_failure reason=invalid_token method=%s path=%s", method, path)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user = await db.scalar(select(User).where(User.clerk_user_id == clerk_user_id))
    if user is None:
        log.info("auth_failure reason=user_not_found clerk_user_id=%s method=%s path=%s", clerk_user_id, method, path)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if user.deleted_at is not None:
        log.info(
            "auth_failure reason=user_deleted clerk_user_id=%s deletion_state=%s method=%s path=%s",
            clerk_user_id,
            user.deletion_state,
            method,
            path,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if not user.is_active:
        log.info("auth_failure reason=user_inactive clerk_user_id=%s method=%s path=%s", clerk_user_id, method, path)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    now = datetime.now(timezone.utc)
    if user.last_active_at is None or (now - user.last_active_at) > _LAST_ACTIVE_THROTTLE:
        user.last_active_at = now
        await db.commit()

    return user


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin required")
    return current_user


async def require_superuser(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superuser required")
    return current_user
