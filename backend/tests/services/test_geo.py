"""Tests for app/services/geo.py — IP anonymization and geo lookup."""

from unittest.mock import MagicMock, patch

from app.services.geo import anonymize_ip, get_geo


class TestAnonymizeIp:
    def test_ipv4_zeros_last_octet(self):
        assert anonymize_ip("203.0.113.42") == "203.0.113.0"

    def test_ipv4_last_octet_already_zero(self):
        assert anonymize_ip("10.0.0.0") == "10.0.0.0"

    def test_ipv4_preserves_first_three_octets(self):
        result = anonymize_ip("192.168.1.255")
        assert result == "192.168.1.0"

    def test_ipv4_loopback(self):
        assert anonymize_ip("127.0.0.1") == "127.0.0.0"

    def test_ipv6_zeros_after_48_bits(self):
        result = anonymize_ip("2001:db8:1234:5678:abcd:ef01:2345:6789")
        assert result.startswith("2001:db8:1234:")
        assert result == "2001:db8:1234::"

    def test_ipv6_loopback(self):
        assert anonymize_ip("::1") == "::"

    def test_ipv6_link_local(self):
        result = anonymize_ip("fe80::1ff:fe23:4567:890a")
        assert result.startswith("fe80::")

    def test_invalid_ip_returned_unchanged(self):
        assert anonymize_ip("not-an-ip") == "not-an-ip"

    def test_empty_string_returned_unchanged(self):
        assert anonymize_ip("") == ""


class TestGetGeo:
    def _make_mock_response(self, country_iso="US", subdivision_iso="CA", city="San Francisco"):
        response = MagicMock()
        response.country.iso_code = country_iso
        response.city.name = city
        most_specific = MagicMock()
        most_specific.iso_code = subdivision_iso
        response.subdivisions.most_specific = most_specific
        return response

    def test_returns_geo_dict_on_success(self):
        mock_response = self._make_mock_response()
        mock_reader = MagicMock()
        mock_reader.__enter__ = MagicMock(return_value=mock_reader)
        mock_reader.__exit__ = MagicMock(return_value=False)
        mock_reader.city.return_value = mock_response

        with patch("geoip2.database.Reader", return_value=mock_reader):
            result = get_geo("203.0.113.0")

        assert result == {"country_iso": "US", "subdivision": "CA", "city": "San Francisco"}

    def test_returns_empty_dict_when_mmdb_missing(self):
        with patch("geoip2.database.Reader", side_effect=FileNotFoundError("/app/data/GeoLite2-City.mmdb")):
            result = get_geo("203.0.113.0")
        assert result == {}

    def test_returns_empty_dict_on_lookup_exception(self):
        mock_reader = MagicMock()
        mock_reader.__enter__ = MagicMock(return_value=mock_reader)
        mock_reader.__exit__ = MagicMock(return_value=False)
        mock_reader.city.side_effect = Exception("address not found")

        with patch("geoip2.database.Reader", return_value=mock_reader):
            result = get_geo("0.0.0.0")
        assert result == {}

    def test_handles_none_country_iso(self):
        mock_response = self._make_mock_response(country_iso=None)
        mock_reader = MagicMock()
        mock_reader.__enter__ = MagicMock(return_value=mock_reader)
        mock_reader.__exit__ = MagicMock(return_value=False)
        mock_reader.city.return_value = mock_response

        with patch("geoip2.database.Reader", return_value=mock_reader):
            result = get_geo("10.0.0.0")

        assert result["country_iso"] == ""

    def test_handles_none_city(self):
        mock_response = self._make_mock_response(city=None)
        mock_reader = MagicMock()
        mock_reader.__enter__ = MagicMock(return_value=mock_reader)
        mock_reader.__exit__ = MagicMock(return_value=False)
        mock_reader.city.return_value = mock_response

        with patch("geoip2.database.Reader", return_value=mock_reader):
            result = get_geo("10.0.0.0")

        assert result["city"] == ""

    def test_returns_all_expected_keys_on_success(self):
        mock_response = self._make_mock_response()
        mock_reader = MagicMock()
        mock_reader.__enter__ = MagicMock(return_value=mock_reader)
        mock_reader.__exit__ = MagicMock(return_value=False)
        mock_reader.city.return_value = mock_response

        with patch("geoip2.database.Reader", return_value=mock_reader):
            result = get_geo("203.0.113.0")

        assert set(result.keys()) == {"country_iso", "subdivision", "city"}
