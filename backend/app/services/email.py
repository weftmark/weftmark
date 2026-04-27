from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import aiosmtplib

from app.config import get_settings

_TEMPLATES = Path(__file__).parent.parent / "templates" / "email"


def _render(name: str, **kwargs: str) -> tuple[str, str]:
    txt = (_TEMPLATES / f"{name}.txt").read_text().format(**kwargs)
    html = (_TEMPLATES / f"{name}.html").read_text().format(**kwargs)
    return txt, html


async def _send(to: list[str], subject: str, txt: str, html: str) -> None:
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


async def send_pending_signup_notification(admin_emails: list[str], display_name: str, email: str) -> None:
    settings = get_settings()
    txt, html = _render(
        "pending_signup_admin_notification",
        display_name=display_name,
        email=email,
        admin_url=f"{settings.frontend_url}/admin",
    )
    await _send(admin_emails, f"New sign-up waiting for approval — {settings.smtp_from_name}", txt, html)


async def send_signup_received_email(to_email: str, display_name: str) -> None:
    settings = get_settings()
    txt, html = _render(
        "pending_signup_user_confirmation",
        display_name=display_name,
        app_name=settings.smtp_from_name,
    )
    await _send([to_email], f"Your {settings.smtp_from_name} sign-up request was received", txt, html)


async def send_account_approved_email(to_email: str, display_name: str) -> None:
    settings = get_settings()
    txt, html = _render(
        "account_approved",
        display_name=display_name,
        app_name=settings.smtp_from_name,
        login_url=f"{settings.frontend_url}/login",
    )
    await _send([to_email], f"Your {settings.smtp_from_name} account is ready", txt, html)


async def send_account_denied_email(to_email: str, display_name: str) -> None:
    settings = get_settings()
    txt, html = _render(
        "account_denied",
        display_name=display_name,
        app_name=settings.smtp_from_name,
    )
    await _send([to_email], f"Your {settings.smtp_from_name} sign-up request", txt, html)


async def send_approval_confirmation_to_admins(
    admin_emails: list[str], display_name: str, email: str, approved_by: str
) -> None:
    settings = get_settings()
    txt, html = _render(
        "approval_admin_confirmation",
        display_name=display_name,
        email=email,
        approved_by=approved_by,
        app_name=settings.smtp_from_name,
    )
    await _send(admin_emails, f"Account approved — {display_name} ({email})", txt, html)


async def send_invite_email(to_email: str, invite_token: str, expires_days: int) -> None:
    settings = get_settings()
    invite_url = f"{settings.frontend_url}/register?token={invite_token}"

    message = MIMEMultipart("alternative")
    message["Subject"] = f"You've been invited to {settings.smtp_from_name}"
    message["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    message["To"] = to_email

    text_body = (
        f"You've been invited to join {settings.smtp_from_name}.\n\n"
        f"Click the link below to accept your invitation:\n{invite_url}\n\n"
        f"This link expires in {expires_days} day(s) and can only be used once."
    )
    html_body = f"""
    <p>You've been invited to join <strong>{settings.smtp_from_name}</strong>.</p>
    <p><a href="{invite_url}">Accept Invitation</a></p>
    <p>This link expires in {expires_days} day(s) and can only be used once.</p>
    """

    message.attach(MIMEText(text_body, "plain"))
    message.attach(MIMEText(html_body, "html"))

    await aiosmtplib.send(
        message,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password,
        start_tls=True,
    )
