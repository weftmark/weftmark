"""Tests for app.tasks.cve_scan._do_scan, _run_pip_audit, _scan_npm_osv, _store_summary."""

import json
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

from app.tasks.cve_scan import CVE_SUMMARY_KEY, _do_scan, _run_pip_audit, _scan_npm_osv, _store_summary

# ---------------------------------------------------------------------------
# TestRunPipAudit — subprocess-backed pip-audit wrapper
# ---------------------------------------------------------------------------


class TestRunPipAudit:
    def _mock_run(self, stdout: str, returncode: int = 0):
        r = MagicMock()
        r.stdout = stdout
        r.returncode = returncode
        return r

    def test_returns_empty_list_when_no_vulns(self):
        pkg_json = json.dumps([{"name": "requests", "version": "2.28.0", "vulns": []}])
        with patch("subprocess.run", return_value=self._mock_run(pkg_json)):
            result = _run_pip_audit()
        assert result == []

    def test_returns_finding_for_vulnerable_package(self):
        vuln = {
            "id": "GHSA-xxxx",
            "aliases": ["CVE-2023-0001"],
            "fix_versions": ["2.29.0"],
            "description": "A test vulnerability",
        }
        pkg_json = json.dumps([{"name": "requests", "version": "2.28.0", "vulns": [vuln]}])
        with patch("subprocess.run", return_value=self._mock_run(pkg_json)):
            result = _run_pip_audit()
        assert len(result) == 1
        assert result[0]["name"] == "requests"
        assert len(result[0]["vulns"]) == 1

    def test_returns_empty_list_when_pip_audit_missing(self):
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = _run_pip_audit()
        assert result == []

    def test_returns_empty_list_on_subprocess_error(self):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("pip-audit", 120)):
            result = _run_pip_audit()
        assert result == []

    def test_handles_empty_stdout(self):
        with patch("subprocess.run", return_value=self._mock_run("")):
            result = _run_pip_audit()
        assert result == []

    def test_filters_packages_without_vulns(self):
        pkg_json = json.dumps(
            [
                {"name": "safe-pkg", "version": "1.0.0", "vulns": []},
                {"name": "bad-pkg", "version": "1.0.0", "vulns": [{"id": "CVE-1", "aliases": [], "fix_versions": []}]},
            ]
        )
        with patch("subprocess.run", return_value=self._mock_run(pkg_json)):
            result = _run_pip_audit()
        assert len(result) == 1
        assert result[0]["name"] == "bad-pkg"


# ---------------------------------------------------------------------------
# TestScanNpmOsv — async OSV.dev API scan
# ---------------------------------------------------------------------------


class TestScanNpmOsv:
    async def test_returns_empty_list_for_empty_deps(self):
        result = await _scan_npm_osv({})
        assert result == []

    async def test_returns_empty_list_on_http_error(self):
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("network error"))
        mock_cls = MagicMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", mock_cls):
            result = await _scan_npm_osv({"react": "18.0.0"})
        assert result == []

    async def test_returns_findings_for_vulnerable_npm_package(self):
        osv_response = {
            "results": [{"vulns": [{"id": "GHSA-npm-1", "aliases": [], "summary": "npm vuln", "details": ""}]}]
        }
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = osv_response

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_cls = MagicMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", mock_cls):
            result = await _scan_npm_osv({"vulnerable-pkg": "1.0.0"})

        assert len(result) == 1
        assert result[0]["name"] == "vulnerable-pkg"

    async def test_returns_empty_for_packages_with_no_vulns(self):
        osv_response = {"results": [{"vulns": []}]}
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = osv_response

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_cls = MagicMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", mock_cls):
            result = await _scan_npm_osv({"safe-pkg": "1.0.0"})

        assert result == []


# ---------------------------------------------------------------------------
# TestStoreSummary — Redis summary write
# ---------------------------------------------------------------------------


class TestCveStoreSummary:
    def test_writes_to_correct_redis_key(self):
        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_client = MagicMock()

        with patch("redis.from_url", return_value=mock_client):
            _store_summary(mock_settings, 3, "2026-01-01T00:00:00+00:00")

        key = mock_client.set.call_args[0][0]
        assert key == CVE_SUMMARY_KEY

    def test_stores_finding_count(self):
        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_client = MagicMock()

        with patch("redis.from_url", return_value=mock_client):
            _store_summary(mock_settings, 7, "2026-01-01T00:00:00+00:00")

        _key, value = mock_client.set.call_args[0]
        data = json.loads(value)
        assert data["finding_count"] == 7

    def test_swallows_redis_exception(self):
        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379/0"

        with patch("redis.from_url", side_effect=Exception("redis down")):
            _store_summary(mock_settings, 0, "2026-01-01T00:00:00+00:00")  # must not raise

    def test_stores_scanned_at(self):
        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_client = MagicMock()
        ts = "2026-05-18T10:00:00+00:00"

        with patch("redis.from_url", return_value=mock_client):
            _store_summary(mock_settings, 0, ts)

        _key, value = mock_client.set.call_args[0]
        data = json.loads(value)
        assert data["scanned_at"] == ts


# ---------------------------------------------------------------------------
# TestDoScan — integration of the above
# ---------------------------------------------------------------------------


class TestDoScan:
    async def test_returns_expected_keys(self):
        with (
            patch("app.tasks.cve_scan._run_pip_audit", return_value=[]),
            patch("app.tasks.cve_scan._scan_npm_osv", new=AsyncMock(return_value=[])),
            patch("app.tasks.cve_scan._store_summary"),
            patch("app.config.get_settings", return_value=MagicMock()),
        ):
            result = await _do_scan({})

        for key in ("backend_findings", "frontend_findings", "scanned_at", "total_findings"):
            assert key in result

    async def test_total_findings_sums_both_sources(self):
        backend = [{"name": "pkg", "version": "1.0", "vulns": [{"id": "CVE-1"}]}]
        frontend = [{"name": "npm-pkg", "version": "1.0", "vulns": [{"id": "CVE-2"}, {"id": "CVE-3"}]}]

        with (
            patch("app.tasks.cve_scan._run_pip_audit", return_value=backend),
            patch("app.tasks.cve_scan._scan_npm_osv", new=AsyncMock(return_value=frontend)),
            patch("app.tasks.cve_scan._store_summary"),
            patch("app.config.get_settings", return_value=MagicMock()),
        ):
            result = await _do_scan({})

        assert result["total_findings"] == 3

    async def test_calls_store_summary(self):
        with (
            patch("app.tasks.cve_scan._run_pip_audit", return_value=[]),
            patch("app.tasks.cve_scan._scan_npm_osv", new=AsyncMock(return_value=[])),
            patch("app.tasks.cve_scan._store_summary") as mock_store,
            patch("app.config.get_settings", return_value=MagicMock()),
        ):
            await _do_scan({})

        mock_store.assert_called_once()
