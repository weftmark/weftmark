from datetime import datetime, timezone
from pathlib import Path

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
    from app.tasks.email_task import send_email

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
    queued_at = datetime.now(timezone.utc).isoformat()
    task = send_email.delay(to=to, subject=subject, txt=txt, html=html, queued_at=queued_at)
    from app.services.task_history import record_queued

    record_queued(settings, task.id, "app.tasks.email_task.send_email", "email")


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


def _format_uptime(seconds: float) -> str:
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


def _probe_table_txt(probe_rows: list[tuple[str, bool, str]]) -> str:
    lines = []
    for name, ok, detail in probe_rows:
        status = "OK  " if ok else "FAIL"
        line = f"  {status}  {name}"
        if detail:
            line += f" — {detail}"
        lines.append(line)
    return "\n".join(lines) if lines else "  (no probes)"


def _probe_table_html(probe_rows: list[tuple[str, bool, str]]) -> str:
    rows = []
    for i, (name, ok, detail) in enumerate(probe_rows):
        bg = "#f9fafb" if i % 2 == 0 else "#f3f4f6"
        status_color = "#16a34a" if ok else "#dc2626"
        status_label = "OK" if ok else "FAIL"
        detail_cell = f" &mdash; <span style='color:#6b7280'>{detail}</span>" if detail else ""
        td1 = (
            f'<td style="padding:8px 16px;font-size:13px;font-family:monospace;'
            f'color:{status_color};white-space:nowrap;">{status_label}</td>'
        )
        td2 = f'<td style="padding:8px 16px;font-size:13px;white-space:nowrap;">{name}{detail_cell}</td>'
        rows.append(f'<tr style="background:{bg};">{td1}{td2}</tr>')
    fallback = '<tr><td colspan="2" style="padding:8px 16px;font-size:13px;color:#6b7280;">(no probes)</td></tr>'
    inner = "".join(rows) or fallback
    return (
        '<table width="100%" cellpadding="0" cellspacing="0" '
        'style="border-collapse:collapse;margin:0 0 20px;background:#f9fafb;border-radius:6px;overflow:hidden;">'
        + inner
        + "</table>"
    )


async def send_stack_startup_alert(
    superuser_emails: list[str],
    env: str,
    app_base_url: str,
    version: str,
    worker_version: str | None,
    probe_status: str,
    probe_rows: list[tuple[str, bool, str]],
    timestamp: str,
) -> None:
    settings = get_settings()
    if not settings.smtp_user or not superuser_emails:
        return
    has_failures = probe_status in ("degraded", "error")
    event_label = "Started with warnings" if has_failures else "Started"
    admin_url = f"{app_base_url}/admin" if app_base_url else f"{settings.frontend_url}/admin"
    worker_ver_str = worker_version or "unknown"
    if has_failures:
        banner_bg, banner_border, banner_text = "#fef2f2", "#dc2626", "#b91c1c"
        failure_note = "One or more startup probes reported a failure. See the table above for details."
        failure_note_html = (
            '<p style="margin:0 0 16px;font-size:14px;color:#b91c1c;font-weight:bold;">'
            "One or more startup probes reported a failure. See the table above for details.</p>"
        )
    else:
        banner_bg, banner_border, banner_text = "#f0fdf4", "#16a34a", "#15803d"
        failure_note = ""
        failure_note_html = ""
    txt, html = _render(
        "stack_startup_alert",
        env=env,
        app_base_url=app_base_url,
        version=version,
        worker_version=worker_ver_str,
        event_label=event_label,
        timestamp=timestamp,
        admin_url=admin_url,
        probe_table_txt=_probe_table_txt(probe_rows),
        probe_table_html=_probe_table_html(probe_rows),
        failure_note=failure_note,
        failure_note_html=failure_note_html,
        banner_bg=banner_bg,
        banner_border=banner_border,
        banner_text=banner_text,
    )
    subject = f"[{settings.app_name} {env}] Stack {event_label} — {timestamp}"
    await _send(superuser_emails, subject, txt, html)


async def send_stack_shutdown_alert(
    superuser_emails: list[str],
    env: str,
    app_base_url: str,
    version: str,
    uptime_seconds: float,
    timestamp: str,
) -> None:
    settings = get_settings()
    if not settings.smtp_user or not superuser_emails:
        return
    admin_url = f"{app_base_url}/admin" if app_base_url else f"{settings.frontend_url}/admin"
    txt, html = _render(
        "stack_shutdown_alert",
        env=env,
        app_base_url=app_base_url,
        version=version,
        uptime_str=_format_uptime(uptime_seconds),
        timestamp=timestamp,
        admin_url=admin_url,
    )
    subject = f"[{settings.app_name} {env}] Stack Stopped — {timestamp}"
    await _send(superuser_emails, subject, txt, html)


async def send_health_degraded_alert(
    superuser_emails: list[str],
    env: str,
    app_base_url: str,
    version: str,
    probe_rows: list[tuple[str, bool, str]],
    status: str,
    timestamp: str,
) -> None:
    settings = get_settings()
    if not settings.smtp_user or not superuser_emails:
        return
    admin_url = f"{app_base_url}/admin" if app_base_url else f"{settings.frontend_url}/admin"
    status_label = "Error" if status == "error" else "Degraded"
    txt, html = _render(
        "health_degraded_alert",
        env=env,
        app_base_url=app_base_url,
        version=version,
        status_label=status_label,
        timestamp=timestamp,
        admin_url=admin_url,
        probe_table_txt=_probe_table_txt(probe_rows),
        probe_table_html=_probe_table_html(probe_rows),
    )
    subject = f"[{settings.app_name} {env}] Health {status_label} — {timestamp}"
    await _send(superuser_emails, subject, txt, html)


async def send_health_recovered_alert(
    superuser_emails: list[str],
    env: str,
    app_base_url: str,
    version: str,
    timestamp: str,
) -> None:
    settings = get_settings()
    if not settings.smtp_user or not superuser_emails:
        return
    admin_url = f"{app_base_url}/admin" if app_base_url else f"{settings.frontend_url}/admin"
    txt, html = _render(
        "health_recovered_alert",
        env=env,
        app_base_url=app_base_url,
        version=version,
        timestamp=timestamp,
        admin_url=admin_url,
    )
    subject = f"[{settings.app_name} {env}] Health Recovered — {timestamp}"
    await _send(superuser_emails, subject, txt, html)


async def send_test_email(to_email: str) -> None:
    settings = get_settings()
    txt, html = _render("test_email")
    await _send([to_email], f"{settings.app_name} — SMTP Test", txt, html)


async def send_invite_email(
    to_email: str, invite_token: str, expires_days: int, admin_name: str = "A weftmark admin"
) -> None:
    settings = get_settings()
    invite_url = f"{settings.frontend_url}/register?token={invite_token}"
    txt, html = _render("invite", invite_url=invite_url, expires_days=expires_days, admin_name=admin_name)
    await _send([to_email], f"{admin_name} has invited you to join {settings.app_name}", txt, html)
