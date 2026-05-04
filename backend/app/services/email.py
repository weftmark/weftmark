from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import aiosmtplib

from app.config import get_settings

_TEMPLATES = Path(__file__).parent.parent / "templates" / "email"


def _render(name: str, **kwargs) -> tuple[str, str]:
    settings = get_settings()
    kwargs.setdefault("app_name", settings.app_name)
    kwargs.setdefault("frontend_url", settings.frontend_url)
    raw_base_html = (_TEMPLATES / "_base.html").read_text()
    raw_base_txt = (_TEMPLATES / "_base.txt").read_text()
    raw_body_html = (_TEMPLATES / f"{name}.html").read_text()
    raw_body_txt = (_TEMPLATES / f"{name}.txt").read_text()
    html = raw_base_html.replace("__BODY__", raw_body_html).format(**kwargs)
    txt = raw_base_txt.replace("__BODY__", raw_body_txt).format(**kwargs)
    return txt, html


async def _send(to: list[str], subject: str, txt: str, html: str) -> None:
    settings = get_settings()
    if settings.app_env == "dev":
        subject = f"[DEV] {subject}"
        txt = "*** DEV ENVIRONMENT — this email was sent from a non-production system ***\n\n" + txt
        html = html.replace(
            "<!-- DEV_BANNER -->",
            '<div style="background:#f59e0b;color:#000;font-weight:bold;padding:8px 12px;'
            'font-family:Arial,Helvetica,sans-serif;">'
            "DEV ENVIRONMENT — this email was sent from a non-production system"
            "</div>",
        )
    else:
        html = html.replace("<!-- DEV_BANNER -->", "")
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
    await _send(admin_emails, f"New sign-up waiting for approval — {settings.app_name}", txt, html)


async def send_signup_received_email(to_email: str, display_name: str) -> None:
    settings = get_settings()
    txt, html = _render("pending_signup_user_confirmation", display_name=display_name)
    await _send([to_email], f"Your {settings.app_name} sign-up request was received", txt, html)


async def send_account_approved_email(to_email: str, display_name: str) -> None:
    settings = get_settings()
    txt, html = _render(
        "account_approved",
        display_name=display_name,
        login_url=f"{settings.frontend_url}/login",
    )
    await _send([to_email], f"Your {settings.app_name} account is ready", txt, html)


async def send_account_denied_email(to_email: str, display_name: str) -> None:
    settings = get_settings()
    txt, html = _render("account_denied", display_name=display_name)
    await _send([to_email], f"Your {settings.app_name} sign-up request", txt, html)


async def send_approval_confirmation_to_admins(
    admin_emails: list[str], display_name: str, email: str, approved_by: str
) -> None:
    txt, html = _render(
        "approval_admin_confirmation",
        display_name=display_name,
        email=email,
        approved_by=approved_by,
    )
    await _send(admin_emails, f"Account approved — {display_name} ({email})", txt, html)


async def send_deletion_created_admin(admin_emails: list[str], display_name: str, email: str) -> None:
    settings = get_settings()
    txt, html = _render(
        "deletion_created_admin",
        display_name=display_name,
        email=email,
        admin_url=f"{settings.frontend_url}/admin",
    )
    await _send(admin_emails, f"User deletion queued — {display_name} ({email})", txt, html)


async def send_deletion_completed_admin(admin_emails: list[str], display_name: str, email: str) -> None:
    txt, html = _render("deletion_completed_admin", display_name=display_name, email=email)
    await _send(admin_emails, f"User deletion complete — {display_name} ({email})", txt, html)


async def send_deletion_stalled_superuser(
    superuser_emails: list[str], display_name: str, email: str, user_id: str
) -> None:
    settings = get_settings()
    txt, html = _render(
        "deletion_stalled_superuser",
        display_name=display_name,
        email=email,
        user_id=user_id,
        admin_url=f"{settings.frontend_url}/admin",
    )
    await _send(superuser_emails, f"User deletion stalled — {display_name} ({email})", txt, html)


async def send_test_email(to_email: str) -> None:
    settings = get_settings()
    txt, html = _render("test_email")
    await _send([to_email], f"{settings.app_name} — SMTP Test", txt, html)


async def send_invite_email(
    to_email: str, invite_token: str, expires_days: int, admin_name: str = "A WeftMark admin"
) -> None:
    settings = get_settings()
    invite_url = f"{settings.frontend_url}/register?token={invite_token}"
    txt, html = _render("invite", invite_url=invite_url, expires_days=expires_days, admin_name=admin_name)
    await _send([to_email], f"{admin_name} has invited you to join {settings.app_name}", txt, html)
