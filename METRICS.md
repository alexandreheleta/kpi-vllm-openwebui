# Available Metrics

This document describes all metrics available in this monitoring stack.

## Open WebUI Database Metrics

Exported by the `metrics-exporter` service from Open WebUI's SQLite database.

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `openwebui_users_total` | Gauge | - | Total registered users |
| `openwebui_users_active_30d` | Gauge | - | Users active in last 30 days |
| `openwebui_chats_total` | Gauge | - | Total chat sessions |
| `openwebui_messages_total` | Gauge | - | Total AI responses generated |
| `openwebui_model_usage` | Gauge | `model` | AI responses per model |
| `openwebui_user_messages` | Gauge | `user_name` | AI responses per user |

### Data Source

Metrics are read from `/app/backend/data/webui.db` (SQLite):

```
Tables used:
├── user (id, name, last_active_at, created_at)
└── chat (user_id, chat JSON blob, created_at, updated_at)
    └── chat.messages[] → {role: "assistant"|"user", ...}
    └── chat.models[] → ["model-name", ...]
```

---

## vLLM Metrics

Scraped from vLLM's Prometheus endpoint (`/metrics`).

### Performance Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `vllm:time_to_first_token_seconds` | Histogram | `model_name` | Time until first token generated |
| `vllm:e2e_request_latency_seconds` | Histogram | `model_name` | Total request latency |
| `vllm:prompt_tokens_total` | Counter | `model_name` | Total prompt tokens processed |
| `vllm:generation_tokens_total` | Counter | `model_name` | Total tokens generated |

### Resource Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `vllm:kv_cache_usage_perc` | Gauge | `model_name` | KV cache utilization (0-1) |
| `vllm:num_requests_running` | Gauge | `model_name` | Currently processing requests |
| `vllm:num_requests_waiting` | Gauge | `model_name` | Requests in queue |
| `vllm:gpu_cache_usage_perc` | Gauge | `model_name` | GPU cache utilization |
| `vllm:cpu_cache_usage_perc` | Gauge | `model_name` | CPU cache utilization |

### Request Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `vllm:request_success_total` | Counter | `model_name` | Successful requests |
| `vllm:request_prompt_tokens` | Histogram | `model_name` | Tokens per prompt |
| `vllm:request_generation_tokens` | Histogram | `model_name` | Tokens per response |

---

## Example Queries

### Active Users (30 days)
```promql
openwebui_users_active_30d
```

### Top Users by AI Responses
```promql
topk(10, openwebui_user_messages)
```

### Model Usage Distribution
```promql
openwebui_model_usage
```

### vLLM P95 Latency
```promql
histogram_quantile(0.95, sum by(le) (rate(vllm:e2e_request_latency_seconds_bucket[5m])))
```

### vLLM Token Throughput
```promql
rate(vllm:generation_tokens_total[5m])
```

### KV Cache Usage
```promql
vllm:kv_cache_usage_perc * 100
```

---

## Dashboard Mapping

| Dashboard | Panels | Metrics Used |
|-----------|--------|--------------|
| **Executive KPI** | Active Users | `openwebui_users_active_30d` |
| | Avg Response Time | `vllm:e2e_request_latency_seconds` |
| | Tokens Generated | `vllm:generation_tokens_total` |
| | Model Usage | `openwebui_model_usage` |
| | User Leaderboard | `openwebui_user_messages` |
| **vLLM Operations** | KV Cache | `vllm:kv_cache_usage_perc` |
| | Request Queue | `vllm:num_requests_running`, `vllm:num_requests_waiting` |
| | Time to First Token | `vllm:time_to_first_token_seconds` |
| | E2E Latency | `vllm:e2e_request_latency_seconds` |
| | HTTP Requests/s | `http_request_duration_seconds_count` |
| | HTTP Response Time | `http_request_duration_seconds_bucket` |
| | Token Throughput | `vllm:prompt_tokens_total`, `vllm:generation_tokens_total` |
