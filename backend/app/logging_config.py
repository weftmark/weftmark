from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

# Standard LogRecord attributes — extras beyond these are included in the output.
_STDLIB_ATTRS = frozenset(
    {
        "args",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class TraceContextFilter(logging.Filter):
    """Inject trace_id/span_id from the active OTel span into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from opentelemetry import trace

            ctx = trace.get_current_span().get_span_context()
            if ctx.is_valid:
                record.trace_id = format(ctx.trace_id, "032x")
                record.span_id = format(ctx.span_id, "016x")
        except Exception:
            pass
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["exc_info"] = self.formatException(record.exc_info)
        for key, val in record.__dict__.items():
            if key not in _STDLIB_ATTRS and not key.startswith("_"):
                try:
                    json.dumps(val)
                    entry[key] = val
                except (TypeError, ValueError):
                    entry[key] = str(val)
        return json.dumps(entry)


def configure_logging(log_level: str) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(TraceContextFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False

    # CeleryInstrumentor emits a WARNING for every task when Celery attaches a
    # dict extra to log records — the SDK skips the attribute safely, so this
    # is pure noise.  Raise to ERROR to keep Loki clean.
    logging.getLogger("opentelemetry.attributes").setLevel(logging.ERROR)
