"""Tests for app/tasks/geo.refresh_geoip_database.

Covers: license-key guard, staleness guard, download + extract path, missing-file path.
"""

import os
import tarfile
import time
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from app.tasks.geo import _MIN_AGE_SECONDS, refresh_geoip_database


def _make_fake_tar_gz(mmdb_content: bytes = b"fake-mmdb") -> bytes:
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo(name="GeoLite2-City_20240101/GeoLite2-City.mmdb")
        info.size = len(mmdb_content)
        tf.addfile(info, BytesIO(mmdb_content))
    return buf.getvalue()


def _mock_settings(license_key: str, db_path: str) -> MagicMock:
    settings = MagicMock()
    settings.maxmind_license_key = license_key
    settings.geoip_db_path = db_path
    return settings


class TestRefreshGeoipDatabase:
    def test_skips_when_no_license_key(self, tmp_path):
        db_path = str(tmp_path / "GeoLite2-City.mmdb")
        with patch("app.config.get_settings", return_value=_mock_settings("", db_path)):
            result = refresh_geoip_database()
        assert result["skipped"] is True
        assert result["reason"] == "no_license_key"

    def test_skips_when_file_is_fresh(self, tmp_path):
        db_path = tmp_path / "GeoLite2-City.mmdb"
        db_path.write_bytes(b"existing")
        # mtime = now — well within the 23 h window
        with patch("app.config.get_settings", return_value=_mock_settings("key", str(db_path))):
            result = refresh_geoip_database()
        assert result["skipped"] is True
        assert result["reason"] == "fresh"

    def test_skips_when_file_just_under_min_age(self, tmp_path):
        db_path = tmp_path / "GeoLite2-City.mmdb"
        db_path.write_bytes(b"existing")
        new_mtime = time.time() - (_MIN_AGE_SECONDS - 60)
        os.utime(db_path, (new_mtime, new_mtime))
        with patch("app.config.get_settings", return_value=_mock_settings("key", str(db_path))):
            result = refresh_geoip_database()
        assert result["skipped"] is True

    def test_downloads_when_file_absent(self, tmp_path):
        db_path = str(tmp_path / "GeoLite2-City.mmdb")
        fake_tar = _make_fake_tar_gz(b"mmdb-data")

        def fake_retrieve(url, dest):
            with open(dest, "wb") as f:
                f.write(fake_tar)

        with (
            patch("app.config.get_settings", return_value=_mock_settings("key", db_path)),
            patch("urllib.request.urlretrieve", side_effect=fake_retrieve),
        ):
            result = refresh_geoip_database()

        assert result.get("refreshed") is True
        assert open(db_path, "rb").read() == b"mmdb-data"

    def test_downloads_when_file_is_stale(self, tmp_path):
        db_path = tmp_path / "GeoLite2-City.mmdb"
        db_path.write_bytes(b"old-data")
        stale_mtime = time.time() - (_MIN_AGE_SECONDS + 3600)
        os.utime(db_path, (stale_mtime, stale_mtime))
        fake_tar = _make_fake_tar_gz(b"new-mmdb-data")

        def fake_retrieve(url, dest):
            with open(dest, "wb") as f:
                f.write(fake_tar)

        with (
            patch("app.config.get_settings", return_value=_mock_settings("key", str(db_path))),
            patch("urllib.request.urlretrieve", side_effect=fake_retrieve),
        ):
            result = refresh_geoip_database()

        assert result.get("refreshed") is True
        assert open(db_path, "rb").read() == b"new-mmdb-data"

    def test_raises_when_mmdb_not_in_archive(self, tmp_path):
        db_path = str(tmp_path / "GeoLite2-City.mmdb")
        buf = BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            info = tarfile.TarInfo(name="some-other-file.txt")
            info.size = 4
            tf.addfile(info, BytesIO(b"data"))
        empty_tar = buf.getvalue()

        def fake_retrieve(url, dest):
            with open(dest, "wb") as f:
                f.write(empty_tar)

        with (
            patch("app.config.get_settings", return_value=_mock_settings("key", db_path)),
            patch("urllib.request.urlretrieve", side_effect=fake_retrieve),
        ):
            with pytest.raises(RuntimeError, match="GeoLite2-City.mmdb not found"):
                refresh_geoip_database()
