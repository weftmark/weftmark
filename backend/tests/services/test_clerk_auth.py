"""Tests for app.services.clerk_auth."""

import base64
from unittest.mock import MagicMock, patch

import pytest

from app.services.clerk_auth import jwks_url_from_publishable_key, verify_session_token


def _make_pk(domain: str, kind: str = "test") -> str:
    """Build a fake Clerk publishable key for a given domain."""
    encoded = base64.urlsafe_b64encode(f"{domain}$".encode()).decode().rstrip("=")
    return f"pk_{kind}_{encoded}"


class TestJwksUrlFromPublishableKey:
    def test_derives_url_from_test_key(self):
        pk = _make_pk("clerk.example.com")
        url = jwks_url_from_publishable_key(pk)
        assert url == "https://clerk.example.com/.well-known/jwks.json"

    def test_derives_url_from_live_key(self):
        pk = _make_pk("clerk.prod.example.com", kind="live")
        url = jwks_url_from_publishable_key(pk)
        assert url == "https://clerk.prod.example.com/.well-known/jwks.json"

    def test_raises_on_malformed_key(self):
        with pytest.raises(Exception):
            jwks_url_from_publishable_key("not_a_valid_key")

    def test_raises_on_too_few_parts(self):
        with pytest.raises(ValueError):
            jwks_url_from_publishable_key("pk_test")


class TestVerifySessionToken:
    def test_returns_sub_on_valid_token(self):
        mock_client = MagicMock()
        mock_signing_key = MagicMock()
        mock_signing_key.key = "fake-key"
        mock_client.get_signing_key_from_jwt.return_value = mock_signing_key

        with patch("app.services.clerk_auth._jwks_client", return_value=mock_client):
            with patch("app.services.clerk_auth.jwt.decode", return_value={"sub": "user_abc123"}):
                result = verify_session_token("fake.jwt.token", "https://example.com/.well-known/jwks.json")

        assert result == "user_abc123"

    def test_returns_none_on_exception(self):
        mock_client = MagicMock()
        mock_client.get_signing_key_from_jwt.side_effect = Exception("invalid token")

        with patch("app.services.clerk_auth._jwks_client", return_value=mock_client):
            result = verify_session_token("bad.token", "https://example.com/.well-known/jwks.json")

        assert result is None

    def test_returns_none_when_sub_missing(self):
        mock_client = MagicMock()
        mock_signing_key = MagicMock()
        mock_signing_key.key = "fake-key"
        mock_client.get_signing_key_from_jwt.return_value = mock_signing_key

        with patch("app.services.clerk_auth._jwks_client", return_value=mock_client):
            with patch("app.services.clerk_auth.jwt.decode", return_value={}):
                result = verify_session_token("fake.jwt.token", "https://example.com/.well-known/jwks.json")

        assert result is None

    def test_returns_none_when_azp_mismatch(self):
        mock_client = MagicMock()
        mock_signing_key = MagicMock()
        mock_signing_key.key = "fake-key"
        mock_client.get_signing_key_from_jwt.return_value = mock_signing_key

        payload = {"sub": "user_abc", "azp": "pk_test_other_app"}
        with patch("app.services.clerk_auth._jwks_client", return_value=mock_client):
            with patch("app.services.clerk_auth.jwt.decode", return_value=payload):
                result = verify_session_token(
                    "fake.jwt.token",
                    "https://example.com/.well-known/jwks.json",
                    expected_azp="pk_test_this_app",
                )

        assert result is None

    def test_returns_sub_when_azp_matches(self):
        mock_client = MagicMock()
        mock_signing_key = MagicMock()
        mock_signing_key.key = "fake-key"
        mock_client.get_signing_key_from_jwt.return_value = mock_signing_key

        payload = {"sub": "user_abc", "azp": "pk_test_this_app"}
        with patch("app.services.clerk_auth._jwks_client", return_value=mock_client):
            with patch("app.services.clerk_auth.jwt.decode", return_value=payload):
                result = verify_session_token(
                    "fake.jwt.token",
                    "https://example.com/.well-known/jwks.json",
                    expected_azp="pk_test_this_app",
                )

        assert result == "user_abc"

    def test_skips_azp_check_when_expected_azp_empty(self):
        mock_client = MagicMock()
        mock_signing_key = MagicMock()
        mock_signing_key.key = "fake-key"
        mock_client.get_signing_key_from_jwt.return_value = mock_signing_key

        # No azp in payload, no expected_azp — should still return sub
        payload = {"sub": "user_abc"}
        with patch("app.services.clerk_auth._jwks_client", return_value=mock_client):
            with patch("app.services.clerk_auth.jwt.decode", return_value=payload):
                result = verify_session_token("fake.jwt.token", "https://example.com/.well-known/jwks.json")

        assert result == "user_abc"
