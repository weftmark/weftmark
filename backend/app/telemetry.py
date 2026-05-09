from __future__ import annotations

import logging
import os

log = logging.getLogger(__name__)

_configured = False


def configure_telemetry(settings) -> None:
    """
    Configure OpenTelemetry SDK: TracerProvider, MeterProvider, LoggerProvider.
    No-ops when OTEL_EXPORTER_OTLP_ENDPOINT is unset (safe in local dev).
    Call once at process startup before constructing FastAPI / Celery app.
    """
    global _configured
    if _configured:
        return

    if not settings.otel_exporter_otlp_endpoint:
        return

    try:
        from opentelemetry import metrics, trace
        from opentelemetry._logs import set_logger_provider
        from opentelemetry.exporter.otlp.proto.http.log_exporter import OTLPLogExporter
        from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.botocore import BotocoreInstrumentor
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        from opentelemetry.instrumentation.logging import LoggingInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        from app.version import VERSION

        resource = Resource.create(
            {
                SERVICE_NAME: os.environ.get("OTEL_SERVICE_NAME", "weftmark"),
                SERVICE_VERSION: VERSION,
                "deployment.environment": settings.app_env,
            }
        )

        # Traces — OTLPSpanExporter reads OTEL_EXPORTER_OTLP_ENDPOINT from env,
        # appends /v1/traces automatically when endpoint param is omitted.
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(tracer_provider)

        # Metrics
        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
        )
        metrics.set_meter_provider(meter_provider)

        # Logs — bridge Python logging → OTel log pipeline → Loki
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
        set_logger_provider(logger_provider)

        # Auto-instrumentors (S3/httpx covered by botocore + httpx instrumentors)
        from opentelemetry.instrumentation.celery import CeleryInstrumentor

        SQLAlchemyInstrumentor().instrument()
        HTTPXClientInstrumentor().instrument()
        BotocoreInstrumentor().instrument()
        CeleryInstrumentor().instrument()
        # Bridge Python log records to OTel without overriding our JSON formatter
        LoggingInstrumentor().instrument(set_logging_format=False)

        _configured = True
        log.info("OpenTelemetry configured", extra={"otlp_endpoint": settings.otel_exporter_otlp_endpoint})

    except Exception:
        log.exception("Failed to configure OpenTelemetry — continuing without telemetry")
