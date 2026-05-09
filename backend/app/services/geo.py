"""GeoIP helpers using the local GeoLite2-City MMDB.

IP anonymization applies GDPR-defensible masking before any lookup or storage:
  IPv4 — zero the last octet  (203.0.113.42 → 203.0.113.0)
  IPv6 — zero all bits after the first 48 (first three 16-bit groups kept)

get_geo() returns an empty dict when the MMDB is absent or the lookup fails so
callers can degrade gracefully without error handling at every call site.
"""

from __future__ import annotations

import ipaddress
import logging

log = logging.getLogger(__name__)


def anonymize_ip(ip: str) -> str:
    """Return anonymized IP; returns the original string unchanged on parse failure."""
    try:
        addr = ipaddress.ip_address(ip)
        if isinstance(addr, ipaddress.IPv4Address):
            parts = str(addr).split(".")
            parts[-1] = "0"
            return ".".join(parts)
        packed = addr.packed
        return str(ipaddress.IPv6Address(packed[:6] + b"\x00" * 10))
    except ValueError:
        return ip


def get_geo(ip: str) -> dict[str, str]:
    """Return geo dict for *ip*; returns {} when MMDB is missing or lookup fails.

    Keys present on success: country_iso, subdivision, city.
    """
    try:
        import geoip2.database

        from app.config import get_settings

        db_path = get_settings().geoip_db_path
        with geoip2.database.Reader(db_path) as reader:
            response = reader.city(ip)
            return {
                "country_iso": response.country.iso_code or "",
                "subdivision": (response.subdivisions.most_specific.iso_code or "") if response.subdivisions else "",
                "city": response.city.name or "",
            }
    except FileNotFoundError:
        log.debug("GeoLite2 MMDB not found — geo lookup skipped")
        return {}
    except Exception:
        log.debug("GeoIP lookup failed for %s", ip, exc_info=True)
        return {}
