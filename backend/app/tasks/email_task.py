"""Celery task: deliver queued transactional email.

Every outbound email is enqueued here rather than sent inline so that:
- HTTP endpoints return immediately regardless of SMTP availability
- Transient SMTP failures are retried with exponential backoff
- Messages that age past the TTL are silently discarded (prevents flood on recovery)
- Messages delayed past the staleness threshold get a banner warning the reader
"""

import asyncio
import logging
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from app.celery_app import celery_app

log = logging.getLogger(__name__)


def _fmt_delay(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m"


async def _do_smtp(to: list[str], subject: str, txt: str, html: str) -> None:
    from app.config import get_settings

    settings = get_settings()
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"] = ", ".join(to)
    msg.attach(MIMEText(txt, "plain"))
    msg.attach(MIMEText(html, "html"))
    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password,
        start_tls=True,
    )


@celery_app.task(
    bind=True,
    name="app.tasks.email_task.send_email",
    max_retries=5,
)
def send_email(
    self,
    *,
    to: list[str],
    subject: str,
    txt: str,
    html: str,
    queued_at: str,
) -> None:
    from app.config import get_settings

    settings = get_settings()
    now = datetime.now(timezone.utc)
    queued_dt = datetime.fromisoformat(queued_at)
    age_s = (now - queued_dt).total_seconds()

    ttl_s = settings.email_ttl_hours * 3600
    if age_s > ttl_s:
        log.warning("email_ttl_expired subject=%r age_s=%.0f ttl_s=%.0f", subject, age_s, ttl_s)
        return

    staleness_s = settings.email_staleness_warning_minutes * 60
    if age_s > staleness_s:
        delay_str = _fmt_delay(age_s)
        note = (
            f"[NOTE: This email was queued at {queued_at} and delivered {delay_str} later. "
            "The information may no longer be current.]\n\n"
        )
        txt = note + txt
        banner = (
            '<div style="background:#fef3c7;border-left:4px solid #f59e0b;padding:10px 16px;'
            'margin:0 0 16px;font-family:Arial,Helvetica,sans-serif;font-size:13px;color:#92400e;">'
            f"&#9888; This notification was queued at {queued_at} and delivered {delay_str} later. "
            "The information may no longer be current.</div>"
        )
        html = html.replace("<!-- STALENESS_BANNER -->", banner)
    else:
        html = html.replace("<!-- STALENESS_BANNER -->", "")

    try:
        asyncio.run(_do_smtp(to, subject, txt, html))
    except Exception as exc:
        countdown = min(60 * (2**self.request.retries), 1800)
        log.warning(
            "email_send_failed subject=%r attempt=%d/%d retry_in=%ds: %s",
            subject,
            self.request.retries + 1,
            self.max_retries + 1,
            countdown,
            exc,
        )
        raise self.retry(exc=exc, countdown=countdown)
