# Open WebUI Monitoring

Grafana dashboards for Open WebUI + vLLM.

## Architecture

```mermaid
flowchart LR
    subgraph app[" "]
        direction TB
        OW[Open WebUI :8080]
        DB[(SQLite)]
        VC[vLLM Coder :8000]
        VH[vLLM Chat :8001]
    end

    subgraph monitoring[" "]
        direction TB
        OTEL[OTEL Collector :4317]
        PROM[(Prometheus)]
        GRAFANA[Grafana :3000]
    end

    EXP[Metrics Exporter]

    OW -->|traces| OTEL
    VC -->|/metrics| OTEL
    VH -->|/metrics| OTEL
    DB -->|read| EXP
    EXP -->|metrics| OTEL
    OTEL --> PROM
    PROM --> GRAFANA
```

## Files

| File | Description |
|------|-------------|
| `supervision-airgap.yml` | Monitoring stack (Grafana, OTEL, metrics exporter) |
| `openwebui-vllm.yml` | Example application stack (for testing only) |
| `airgap-download.sh` | Script to build airgap bundle |

> **Note:** `openwebui-vllm.yml` is provided as a reference example. Use your own Open WebUI and vLLM deployment configuration.

## Configuration (before deployment)

Adapt these files before running the airgap script or deploying:

### 1. `.env` - Credentials and settings

```bash
GF_ADMIN_USER=admin              # Grafana username
GF_ADMIN_PASSWORD=changeme       # Grafana password
EXPORT_INTERVAL=15               # Metrics export interval (seconds)
```

### 2. `otel-config/otelcol-config.yaml` - vLLM endpoints

Update with your vLLM container names and ports:

```yaml
static_configs:
  - targets:
    - vllm-coder:8000      # Change to your vLLM container:port
    - vllm-chat:8001       # Add/remove as many vllm container you run
```

### 3. `supervision-airgap.yml` - Network

If deploying with Open WebUI on the same host, ensure all containers share the same network:

```yaml
networks:
  monitoring:
    external: true         # Uses existing network from Open WebUI and vllm
```

## Airgapped Deployment

For networks without internet access.

### On machine with internet

```bash
chmod +x airgap-download.sh
./airgap-download.sh
```

This creates `airgap-bundle/` containing:
- `otel-lgtm.tar` - Grafana OTEL stack image
- `metrics-exporter.tar` - Pre-built exporter image
- `supervision-airgap.yml` - Docker compose file
- `.env` - Configuration file (edit before deploying)
- Config files (grafana/, otel-config/)

### On airgapped machine

```bash
# Copy airgap-bundle/ to target machine, then:
cd airgap-bundle

# Load images
docker load -i otel-lgtm.tar
docker load -i metrics-exporter.tar

# Edit .env with your settings
docker-compose -f supervision-airgap.yml up -d
```

Access:
- Grafana: http://localhost:3000 (credentials in .env)
- Executive Dashboard: http://localhost:3000/d/openwebui-executive
- vLLM Operations: http://localhost:3000/d/openwebui-vllm-ops

## Generate KPI Report

Generate a formatted KPI report for management:

```bash
# By date range
docker exec metrics-exporter python kpi_report.py 2026-01-01 2026-01-31

# By month
docker exec metrics-exporter python kpi_report.py --month 2026-01

# Export to file
docker exec metrics-exporter python kpi_report.py --month 2026-01 > kpi-2026-01.txt
```

Output:
```
============================================================
KPI REPORT: 2026-01-01 to 2026-01-19
============================================================

KEY METRICS:
  Active Users:                        42
  Total Tokens Generated:       1,250,000
  Avg Response Time:               0.345s

TOKENS BY MODEL:
  Qwen/Qwen2.5-Coder-1.5B-Instruct-AWQ     750,000 ( 60.0%)
  Qwen/Qwen2.5-0.5B-Instruct               500,000 ( 40.0%)

============================================================
```

## Dashboards

Two pre-configured Grafana dashboards are included.

### Executive KPI Dashboard

High-level metrics for management: active users, token usage, model distribution, and user leaderboard.

![Executive KPI Dashboard](images/KPIdashboard.png)

### vLLM Operations Dashboard

Technical monitoring for vLLM performance: request latency, token throughput, KV cache usage, and queue depth.

![vLLM Operations Dashboard](images/vLLMdashboard.png)

## Notes

- vLLM exposes metrics at `/metrics` by default
- Both stacks share the `openwebui-data` volume
- Connect containers to same network for OTEL to work

## Metrics

See [METRICS.md](METRICS.md) for available metrics and queries possible on vllm /metrics and openwebui.

## License

MIT
