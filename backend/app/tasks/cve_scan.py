"""Celery task: CVE / vulnerability scan.

Backend: runs pip-audit (walks full transitive dependency tree via OSV.dev).
Frontend: queries OSV.dev querybatch API directly for each known npm package.
Summary (finding count + timestamp) is stored in Redis for the admin warning banner.
"""

import asyncio
import json
import logging
import subprocess
from datetime import datetime, timezone

from celery import Task

from app.celery_app import celery_app

log = logging.getLogger(__name__)

CVE_SUMMARY_KEY = "weftmark:cve_scan:summary"


@celery_app.task(
    bind=True,
    max_retries=0,
    soft_time_limit=180,
    time_limit=240,
    name="app.tasks.cve_scan.run_cve_scan",
)
def run_cve_scan(self: Task, frontend_deps: dict[str, str]) -> dict:
    return asyncio.run(_do_scan(frontend_deps))


async def _do_scan(frontend_deps: dict[str, str]) -> dict:

    from app.config import get_settings

    settings = get_settings()
    scanned_at = datetime.now(timezone.utc).isoformat()

    backend_findings = _run_pip_audit()
    frontend_findings = await _scan_npm_osv(frontend_deps)

    total = sum(len(f["vulns"]) for f in backend_findings) + sum(len(f["vulns"]) for f in frontend_findings)

    _store_summary(settings, total, scanned_at)

    return {
        "backend_findings": backend_findings,
        "frontend_findings": frontend_findings,
        "scanned_at": scanned_at,
        "total_findings": total,
    }


def _run_pip_audit() -> list[dict]:
    """Run pip-audit and return only packages with vulnerabilities."""
    try:
        result = subprocess.run(
            ["pip-audit", "--format", "json", "--progress-spinner", "off", "-q"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        raw = json.loads(result.stdout or "[]")
        findings = []
        for pkg in raw:
            vulns = pkg.get("vulns") or []
            if not vulns:
                continue
            findings.append(
                {
                    "name": pkg.get("name", ""),
                    "version": pkg.get("version", ""),
                    "vulns": [
                        {
                            "id": v.get("id", ""),
                            "aliases": v.get("aliases") or [],
                            "fix_versions": v.get("fix_versions") or [],
                            "description": v.get("description") or v.get("details") or v.get("summary") or "",
                        }
                        for v in vulns
                    ],
                }
            )
        return findings
    except FileNotFoundError:
        log.warning("pip-audit not found — backend CVE scan skipped")
        return []
    except Exception as exc:
        log.warning("pip-audit error: %s", exc)
        return []


async def _scan_npm_osv(frontend_deps: dict[str, str]) -> list[dict]:
    """Query OSV.dev querybatch API for npm package vulnerabilities."""
    if not frontend_deps:
        return []

    packages = [{"name": name, "version": ver} for name, ver in frontend_deps.items()]
    queries = [{"version": p["version"], "package": {"name": p["name"], "ecosystem": "npm"}} for p in packages]

    try:
        import httpx

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.osv.dev/v1/querybatch",
                json={"queries": queries},
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
    except Exception as exc:
        log.warning("OSV querybatch error: %s", exc)
        return []

    findings = []
    for pkg, osv_result in zip(packages, results):
        vulns_raw = osv_result.get("vulns") or []
        if not vulns_raw:
            continue
        findings.append(
            {
                "name": pkg["name"],
                "version": pkg["version"],
                "vulns": [
                    {
                        "id": v.get("id", ""),
                        "aliases": v.get("aliases") or [],
                        "fix_versions": [],
                        "description": v.get("summary") or v.get("details") or "",
                    }
                    for v in vulns_raw
                ],
            }
        )
    return findings


def _store_summary(settings, finding_count: int, scanned_at: str) -> None:
    try:
        import redis as _redis

        client = _redis.from_url(settings.redis_url, socket_connect_timeout=2)
        client.set(CVE_SUMMARY_KEY, json.dumps({"finding_count": finding_count, "scanned_at": scanned_at}))
        client.close()
    except Exception as exc:
        log.warning("cve_scan summary redis error: %s", exc)
