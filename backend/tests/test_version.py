"""
Tests for app.version.

VERSION is resolved at import time from a VERSION file on disk.
These tests verify the module imports cleanly and returns a valid string.
"""

import re

from app.version import VERSION


class TestVersion:
    def test_version_is_string(self):
        assert isinstance(VERSION, str)

    def test_version_is_non_empty(self):
        assert VERSION.strip() != ""

    def test_version_matches_semver(self):
        assert re.match(r"^\d+\.\d+\.\d+$", VERSION), f"VERSION {VERSION!r} is not semver"

    def test_version_not_default_fallback(self):
        """In a real checkout the VERSION file always exists — should not be 0.0.0."""
        assert VERSION != "0.0.0"
