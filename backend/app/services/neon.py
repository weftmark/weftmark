"""Client for the subset of Neon's Console API this app uses (#1041, formerly inline in
app/routers/admin.py — see #1016/#1032 for the original project-scoped usage panel).

Neon's public API has no invoice/actual-spend endpoint — only a spending *limit* (cap) and
plan tier are exposed, so "billing" here means those two fields, not a dollar-spent figure.
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from pydantic import BaseModel

from app.config import Settings

NEON_API_BASE = "https://console.neon.tech/api/v2"
NEON_CONSUMPTION_URL = f"{NEON_API_BASE}/consumption_history/v2/projects"
NEON_PROJECTS_URL = f"{NEON_API_BASE}/projects"
_REQUEST_TIMEOUT = 10.0


class NeonUsageDay(BaseModel):
    date: str
    compute_seconds: float


class NeonUsageResponse(BaseModel):
    """Trailing-30-day compute usage for a single project."""

    configured: bool
    project_id: str | None = None
    period_start: str | None = None
    total_compute_seconds: float = 0.0
    daily: list[NeonUsageDay] = []
    error: str | None = None


class NeonProjectUsage(BaseModel):
    project_id: str
    project_name: str | None = None
    total_compute_seconds: float


class NeonAccountResponse(BaseModel):
    """Trailing-30-day compute usage across every project in the org, plus whatever
    account-level plan/billing info Neon's API exposes (see module docstring)."""

    configured: bool
    org_name: str | None = None
    plan: str | None = None
    spending_limit_cents: int | None = None
    period_start: str | None = None
    total_compute_seconds: float = 0.0
    daily: list[NeonUsageDay] = []
    by_project: list[NeonProjectUsage] = []
    error: str | None = None


class NeonDashboardResponse(BaseModel):
    account: NeonAccountResponse
    project: NeonUsageResponse


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}


def _parse_consumption(
    data: dict[str, Any], project_id_filter: str | None
) -> tuple[list[NeonUsageDay], float, str | None, dict[str, float]]:
    """Shared parsing for consumption_history/v2/projects — daily totals, grand total,
    the first period_start seen, and a per-project total map (for the account rollup)."""
    daily: list[NeonUsageDay] = []
    total = 0.0
    period_start_out: str | None = None
    by_project: dict[str, float] = {}
    for project in data.get("projects", []):
        pid = project.get("project_id")
        if project_id_filter and pid != project_id_filter:
            continue
        project_total = 0.0
        for period in project.get("periods", []):
            period_start_out = period_start_out or period.get("period_start")
            for point in period.get("consumption", []):
                value = 0.0
                for m in point.get("metrics", []):
                    if m.get("metric_name") == "compute_unit_seconds":
                        value = float(m.get("value", 0))
                daily.append(NeonUsageDay(date=point.get("timeframe_start", ""), compute_seconds=value))
                total += value
                project_total += value
        if pid:
            by_project[pid] = by_project.get(pid, 0.0) + project_total
    return daily, total, period_start_out, by_project


class _NeonHttpError(Exception):
    def __init__(self, status_code: int, text: str) -> None:
        super().__init__(f"Neon API returned HTTP {status_code}")
        self.status_code = status_code
        self.text = text


async def _fetch_consumption(settings: Settings, project_ids: str | None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    params: dict[str, str] = {
        "from": (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "granularity": "daily",
        "org_id": settings.neon_org_id,
        "metrics": "compute_unit_seconds",
    }
    if project_ids:
        params["project_ids"] = project_ids
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
        r = await client.get(NEON_CONSUMPTION_URL, params=params, headers=_auth_headers(settings.neon_api_key))
    if r.status_code != 200:
        raise _NeonHttpError(r.status_code, r.text)
    return dict(r.json())


async def fetch_project_usage(settings: Settings) -> NeonUsageResponse:
    """Trailing 30 days of compute usage for settings.neon_project_id (or all projects
    the org exposes, if unset). Entirely independent of POSTGRES_DSN."""
    if not settings.neon_api_key or not settings.neon_org_id:
        return NeonUsageResponse(configured=False)
    try:
        data = await _fetch_consumption(settings, settings.neon_project_id or None)
    except httpx.TimeoutException:
        return NeonUsageResponse(configured=True, error="Timed out after 10 s")
    except _NeonHttpError as exc:
        return NeonUsageResponse(configured=True, error=str(exc))
    except Exception as exc:
        return NeonUsageResponse(configured=True, error=str(exc)[:200])

    daily, total, period_start, by_project = _parse_consumption(data, settings.neon_project_id or None)
    project_id_out = settings.neon_project_id or (next(iter(by_project), None) if by_project else None)
    return NeonUsageResponse(
        configured=True,
        project_id=project_id_out,
        period_start=period_start,
        total_compute_seconds=total,
        daily=daily,
    )


async def fetch_project_names(settings: Settings) -> dict[str, str]:
    """Best-effort project id -> name map, used to label the account rollup. Empty on any error."""
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            r = await client.get(
                NEON_PROJECTS_URL, params={"org_id": settings.neon_org_id}, headers=_auth_headers(settings.neon_api_key)
            )
        if r.status_code != 200:
            return {}
        return {p["id"]: p.get("name") or p["id"] for p in r.json().get("projects", [])}
    except Exception:
        return {}


async def fetch_org_info(settings: Settings) -> tuple[str | None, str | None, int | None, str | None]:
    """Returns (org_name, plan, spending_limit_cents, error). Neon's org response schema
    isn't fully documented publicly, so field extraction here is defensive/best-effort —
    a parsing miss degrades to None rather than breaking the rest of the dashboard."""
    headers = _auth_headers(settings.neon_api_key)
    org_name: str | None = None
    plan: str | None = None
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            r = await client.get(f"{NEON_API_BASE}/organizations/{settings.neon_org_id}", headers=headers)
        if r.status_code != 200:
            return None, None, None, f"Neon API returned HTTP {r.status_code}"
        org_data = r.json()
        org_name = org_data.get("name")
        plan_field = org_data.get("plan_id") or org_data.get("plan")
        plan = plan_field.get("id") if isinstance(plan_field, dict) else plan_field
    except Exception as exc:
        return None, None, None, str(exc)[:200]

    spending_limit_cents: int | None = None
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            r = await client.get(
                f"{NEON_API_BASE}/organizations/{settings.neon_org_id}/billing/spending_limit", headers=headers
            )
        if r.status_code == 200:
            spending_limit_cents = r.json().get("spending_limit_cents")
        # Non-200 (e.g. 403 on plans below Launch) just leaves the cap unset — not an error.
    except Exception:
        pass

    return org_name, plan, spending_limit_cents, None


async def fetch_account_usage(settings: Settings) -> NeonAccountResponse:
    """Trailing 30 days of compute usage aggregated across every project in the org,
    plus org name/plan/spending-limit where Neon's API makes them available."""
    if not settings.neon_api_key or not settings.neon_org_id:
        return NeonAccountResponse(configured=False)

    org_name, plan, spending_limit_cents, org_error = await fetch_org_info(settings)

    try:
        data = await _fetch_consumption(settings, None)
    except httpx.TimeoutException:
        return NeonAccountResponse(
            configured=True,
            org_name=org_name,
            plan=plan,
            spending_limit_cents=spending_limit_cents,
            error="Timed out after 10 s",
        )
    except _NeonHttpError as exc:
        return NeonAccountResponse(
            configured=True,
            org_name=org_name,
            plan=plan,
            spending_limit_cents=spending_limit_cents,
            error=str(exc),
        )
    except Exception as exc:
        return NeonAccountResponse(
            configured=True,
            org_name=org_name,
            plan=plan,
            spending_limit_cents=spending_limit_cents,
            error=str(exc)[:200],
        )

    daily, total, period_start, by_project = _parse_consumption(data, None)
    names = await fetch_project_names(settings)
    by_project_list = [
        NeonProjectUsage(project_id=pid, project_name=names.get(pid), total_compute_seconds=seconds)
        for pid, seconds in sorted(by_project.items(), key=lambda kv: kv[1], reverse=True)
    ]

    return NeonAccountResponse(
        configured=True,
        org_name=org_name,
        plan=plan,
        spending_limit_cents=spending_limit_cents,
        period_start=period_start,
        total_compute_seconds=total,
        daily=daily,
        by_project=by_project_list,
        error=org_error,
    )


async def fetch_dashboard(settings: Settings) -> NeonDashboardResponse:
    account = await fetch_account_usage(settings)
    project = await fetch_project_usage(settings)
    return NeonDashboardResponse(account=account, project=project)


async def test_connection(v: dict) -> tuple[bool, str, list[dict[str, str]] | None]:
    """Validate neon_api_key/neon_org_id and return a project picker's worth of options.
    Returns (ok, message, options) — mirrors the ConfigTestResult/ConfigTestOption shape
    used by app.routers.admin's service-test endpoint."""
    api_key = v.get("neon_api_key") or ""
    org_id = v.get("neon_org_id") or ""
    if not api_key or not org_id:
        return False, "neon_api_key and neon_org_id are both required", None

    now = datetime.now(timezone.utc)
    params = {
        "from": (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "granularity": "daily",
        "org_id": org_id,
        "metrics": "compute_unit_seconds",
    }
    headers = _auth_headers(api_key)
    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
        resp = await client.get(NEON_CONSUMPTION_URL, params=params, headers=headers)
    if resp.status_code != 200:
        return False, f"Neon API returned {resp.status_code}: {resp.text[:120]}", None
    project_count = len(resp.json().get("projects", []))

    options: list[dict[str, str]] | None = None
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
            proj_resp = await client.get(NEON_PROJECTS_URL, params={"org_id": org_id}, headers=headers)
        if proj_resp.status_code == 200:
            options = [
                {"value": p["id"], "label": p.get("name") or p["id"]} for p in proj_resp.json().get("projects", [])
            ]
    except Exception:
        pass  # project listing is a nice-to-have — the connection test above already succeeded

    return True, f"Connected — {project_count} project(s) visible to this org", options
