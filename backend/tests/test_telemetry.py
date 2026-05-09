"""Tests for app.telemetry — focused on the no-op safety guarantee."""

from unittest.mock import MagicMock, patch


def _make_settings(endpoint: str = ""):
    s = MagicMock()
    s.otel_exporter_otlp_endpoint = endpoint
    s.app_env = "test"
    return s


class TestConfigureTelemetry:
    def setup_method(self):
        # Reset the module-level guard between tests
        import app.telemetry as _mod

        _mod._configured = False

    def test_no_op_when_endpoint_empty(self):
        """No OTel imports or provider setup when endpoint is unset."""
        from app.telemetry import configure_telemetry

        with patch("app.telemetry.log") as mock_log:
            configure_telemetry(_make_settings(endpoint=""))
            mock_log.info.assert_not_called()

    def test_no_op_is_idempotent(self):
        """Calling twice with empty endpoint is safe and does nothing."""
        from app.telemetry import configure_telemetry

        configure_telemetry(_make_settings(endpoint=""))
        configure_telemetry(_make_settings(endpoint=""))  # second call — no error

    def test_configured_flag_prevents_double_init(self):
        """Once configured, a second call with an endpoint is silently ignored."""
        import app.telemetry as _mod

        _mod._configured = True
        from app.telemetry import configure_telemetry

        with patch("app.telemetry.log") as mock_log:
            configure_telemetry(_make_settings(endpoint="http://otelcol:4318"))
            mock_log.info.assert_not_called()

    def test_exception_in_setup_does_not_propagate(self):
        """If OTel setup throws, configure_telemetry catches it and does not crash."""
        from app.telemetry import configure_telemetry

        settings = _make_settings(endpoint="http://otelcol:4318")
        with patch("app.telemetry.log"):
            # Force an import error inside the try block
            with patch.dict("sys.modules", {"opentelemetry": None}):
                configure_telemetry(settings)  # must not raise
