type Level = "debug" | "info" | "warning" | "error";

interface LogEvent {
  level: Level;
  message: string;
  context?: Record<string, unknown>;
}

const ENDPOINT = "/api/logs";
const FLUSH_DELAY_MS = 500;
const MAX_BUFFER = 50;

const buffer: LogEvent[] = [];
let flushTimer: ReturnType<typeof setTimeout> | null = null;

function scheduleFlush(): void {
  if (flushTimer !== null) return;
  flushTimer = setTimeout(flush, FLUSH_DELAY_MS);
}

function flush(): void {
  flushTimer = null;
  if (buffer.length === 0) return;
  const events = buffer.splice(0);
  fetch(ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(events),
  }).catch(() => {
    // Silently swallow — never log-loop if /api/logs is down
  });
}

function emit(level: Level, message: string, context?: Record<string, unknown>): void {
  if (buffer.length >= MAX_BUFFER) return;
  buffer.push({ level, message, context });
  scheduleFlush();
}

export const logger = {
  debug: (message: string, context?: Record<string, unknown>) => emit("debug", message, context),
  info:  (message: string, context?: Record<string, unknown>) => emit("info",  message, context),
  warn:  (message: string, context?: Record<string, unknown>) => emit("warning", message, context),
  error: (message: string, context?: Record<string, unknown>) => emit("error", message, context),
};

export function initLogger(): void {
  window.addEventListener("error", (event) => {
    emit("error", event.message ?? "Uncaught error", {
      source: "window.onerror",
      filename: event.filename,
      lineno: event.lineno,
      colno: event.colno,
    });
  });

  window.addEventListener("unhandledrejection", (event) => {
    const reason = event.reason instanceof Error
      ? event.reason.message
      : String(event.reason);
    emit("error", reason, { source: "unhandledrejection" });
  });
}
