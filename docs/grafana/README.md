# WeftMark Grafana Dashboards

Four importable dashboard JSON files for monitoring the WeftMark API, Celery workers, infrastructure, and distributed traces.

## Dashboards

| File | UID | Description |
|---|---|---|
| `api-overview.json` | `wm-api-overview` | HTTP request rate, error rate, latency percentiles, top routes, error logs |
| `worker-overview.json` | `wm-worker-overview` | Celery task throughput, duration, span call rate, worker/beat error logs |
| `infrastructure.json` | `wm-infrastructure` | Host CPU/memory/disk/network, per-process CPU and RSS |
| `traces-explorer.json` | `wm-traces-explorer` | Span metrics, latency percentiles, top spans table, service map, Loki↔Tempo trace links |

## Importing

1. Open Grafana → **Dashboards → Import**
2. Click **Upload dashboard JSON file** and select one of the files above
3. In the import dialog, map each datasource input to the correct datasource:
   - **Prometheus** → your Prometheus datasource
   - **Loki** → your Loki datasource
   - **Tempo** → your Tempo datasource (traces-explorer only)
4. Click **Import**

### Provisioned datasource UIDs

The observability stack provisions datasources with these UIDs (set in `grafana/provisioning/datasources/datasources.yaml`):

| Datasource | UID |
|---|---|
| Prometheus | `prometheus` |
| Loki | `loki` |
| Tempo | `tempo` |

If you import into the provisioned Grafana instance, selecting the pre-configured datasources in step 3 will match these UIDs and panels will work immediately.

## Template variables

| Variable | Appears in | Purpose |
|---|---|---|
| `datasource` | all | Prometheus instance to query |
| `loki` | api, worker, traces | Loki instance for log panels |
| `tempo` | traces | Tempo instance for service map |
| `server` | api | Filter by `http_server_name` — distinguishes environments (`dev.weftmark.com` vs `weftmark.com`) |
| `service` | traces | Filter spans by service name (`weftmark-api`, `weftmark-worker`) |

## Available data

### Prometheus metrics (confirmed in prod)

| Metric family | Source | Key labels |
|---|---|---|
| `http_server_duration_milliseconds_*` | OTel FastAPI | `job`, `http_target`, `http_status_code`, `http_server_name` |
| `http_server_active_requests` | OTel FastAPI | `job`, `http_server_name` |
| `flower_task_runtime_seconds_*` | Flower | `job`, `task`, `worker` |
| `process_cpu_seconds_total` | OTel process | `job` |
| `process_resident_memory_bytes` | OTel process | `job` |
| `traces_spanmetrics_*` | Tempo metrics gen | `service`, `span_name`, `status_code`, `span_kind` |
| `traces_service_graph_*` | Tempo metrics gen | `client`, `server` |
| `node_*` | node-exporter | standard node labels |

### Known gaps (see open issues)

- No SQLAlchemy connection pool metrics — pool saturation is not observable
- No per-task failure count from CeleryInstrumentor — Flower only exposes runtime histograms for completed tasks, not explicit failure counters
- `deployment_environment` resource attribute does not propagate to HTTP/process metric labels; only appears on `target_info`

### Loki labels

Logs are JSON-formatted. Key fields available for filtering:

- Stream labels: `service_name` (`weftmark-api`, `weftmark-worker`, `weftmark-beat`)
- JSON fields: `level`, `message`, `trace_id`, `span_id`, `logger`

### Tempo services

- `weftmark-api` — HTTP server spans, DB spans, S3 spans
- `weftmark-worker` — Celery task spans, S3 spans, WIF parsing spans, rendering spans (after #514 merges)
