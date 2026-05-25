"""Celery task: weekly refresh of the GeoLite2-City MMDB.

Downloads from MaxMind when MAXMIND_LICENSE_KEY is set.
Skips silently when the key is absent (dev / staging environments without geo).
"""

import logging
import os
import tarfile
import tempfile
import time
import urllib.request

from app.celery_app import celery_app

log = logging.getLogger(__name__)

_MIN_AGE_SECONDS = 23 * 3600  # never download more than once per 23 h


@celery_app.task(
    bind=True,
    max_retries=0,
    name="app.tasks.geo.refresh_geoip_database",
)
def refresh_geoip_database(self) -> dict:
    from app.config import get_settings

    settings = get_settings()
    license_key = settings.maxmind_license_key
    db_path = settings.geoip_db_path

    if not license_key:
        log.info("MAXMIND_LICENSE_KEY not set — skipping GeoLite2 refresh")
        return {"skipped": True, "reason": "no_license_key"}

    if os.path.exists(db_path):
        age = time.time() - os.path.getmtime(db_path)
        if age < _MIN_AGE_SECONDS:
            log.info("GeoLite2-City database is %.1f h old — skipping download", age / 3600)
            return {"skipped": True, "reason": "fresh", "age_hours": round(age / 3600, 1)}

    url = (
        "https://download.maxmind.com/app/geoip_download"
        f"?edition_id=GeoLite2-City&license_key={license_key}&suffix=tar.gz"
    )

    dest_dir = os.path.dirname(db_path)
    os.makedirs(dest_dir, exist_ok=True)

    # Temp dir must be on the same filesystem as db_path so os.replace() (rename) works.
    with tempfile.TemporaryDirectory(dir=dest_dir) as tmpdir:
        archive_path = os.path.join(tmpdir, "GeoLite2-City.tar.gz")
        log.info("Downloading GeoLite2-City database")
        urllib.request.urlretrieve(url, archive_path)  # noqa: S310  # nosec B310  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected

        extracted_mmdb = None
        with tarfile.open(archive_path, "r:gz") as tar:
            for member in tar.getmembers():
                if member.name.endswith("GeoLite2-City.mmdb"):
                    member.name = os.path.basename(member.name)
                    tar.extract(member, tmpdir)
                    extracted_mmdb = os.path.join(tmpdir, "GeoLite2-City.mmdb")
                    break

        if extracted_mmdb is None:
            raise RuntimeError("GeoLite2-City.mmdb not found in downloaded archive")

        os.replace(extracted_mmdb, db_path)

    log.info("GeoLite2-City database refreshed at %s", db_path)
    return {"refreshed": True, "path": db_path}
