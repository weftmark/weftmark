from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from app.config import get_settings


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
