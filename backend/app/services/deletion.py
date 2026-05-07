"""Deletion service — soft-delete a user immediately and dispatch the cascade task.

Called from both the admin panel (superuser-initiated) and the self-service
endpoint (user-initiated, implemented in a later issue).
"""

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

log = logging.getLogger(__name__)


async def initiate_user_deletion(db: AsyncSession, user: User) -> None:
    """Soft-delete the user immediately and queue the background cascade task.

    After this returns the user record has deletion_state='pending' and
    deleted_at set, so all subsequent API requests return 401.
    """
    from app.services.email import send_deletion_created_admin
    from app.tasks.deletion import run_user_deletion

    user.soft_delete()
    user.deletion_state = "pending"
    user.deletion_initiated_at = datetime.now(timezone.utc)
    await db.commit()

    log.info(
        "deletion_initiated user_id=%s email=%s initiated_by=admin",
        user.id,
        user.email,
    )

    _del_task = run_user_deletion.delay(str(user.id))
    from app.config import get_settings
    from app.services.task_history import record_queued

    record_queued(get_settings(), _del_task.id, "app.tasks.deletion.run_user_deletion", "user_deletion")

    # Notify admins that deletion has been queued
    from sqlalchemy import select

    from app.models.user import User as UserModel

    admin_emails_rows = await db.scalars(
        select(UserModel).where(UserModel.is_admin.is_(True), UserModel.deleted_at.is_(None))
    )
    admin_emails = [u.email for u in admin_emails_rows.all()]
    if admin_emails:
        try:
            await send_deletion_created_admin(admin_emails, user.display_name, user.email)
        except Exception as exc:
            log.warning("deletion_notify_failed event=created error=%s", exc)
