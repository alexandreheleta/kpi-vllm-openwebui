#!/usr/bin/env python3
"""
KPI Report Generator for Open WebUI

Queries Prometheus metrics and generates a formatted KPI report for management.

Usage:
    python kpi_report.py 2026-01-01 2026-01-31
    python kpi_report.py --month 2026-01
"""

import argparse
import sys
from calendar import monthrange
from datetime import datetime

import requests

PROMETHEUS_URL = "http://otel-backend:9090"


def parse_args():
    parser = argparse.ArgumentParser(description="Generate KPI report from Prometheus metrics")
    parser.add_argument("start_date", nargs="?", help="Start date (YYYY-MM-DD)")
    parser.add_argument("end_date", nargs="?", help="End date (YYYY-MM-DD)")
    parser.add_argument("--month", "-m", help="Month shortcut (YYYY-MM)")
    parser.add_argument("--prometheus", "-p", default=PROMETHEUS_URL, help="Prometheus URL")
    return parser.parse_args()


def get_date_range(args):
    """Parse date range from arguments."""
    if args.month:
        year, month = map(int, args.month.split("-"))
        start = datetime(year, month, 1)
        _, last_day = monthrange(year, month)
        end = datetime(year, month, last_day, 23, 59, 59)
    elif args.start_date and args.end_date:
        start = datetime.strptime(args.start_date, "%Y-%m-%d")
        end = datetime.strptime(args.end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
    else:
        print("Error: Provide either --month YYYY-MM or start_date end_date")
        sys.exit(1)

    # Cap end date to now (Prometheus has no future data)
    now = datetime.now()
    if end > now:
        end = now

    return start, end


def query_prometheus(prom_url: str, query: str, time: datetime) -> float | None:
    """Execute instant query at specific time."""
    try:
        resp = requests.get(
            f"{prom_url}/api/v1/query",
            params={"query": query, "time": time.timestamp()},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data["status"] == "success" and data["data"]["result"]:
            return float(data["data"]["result"][0]["value"][1])
    except Exception as e:
        print(f"Query failed: {query} - {e}", file=sys.stderr)
    return None


def query_prometheus_vector(prom_url: str, query: str, time: datetime) -> list[tuple[dict, float]]:
    """Execute instant query returning multiple results with labels."""
    try:
        resp = requests.get(
            f"{prom_url}/api/v1/query",
            params={"query": query, "time": time.timestamp()},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data["status"] == "success":
            return [(r["metric"], float(r["value"][1])) for r in data["data"]["result"]]
    except Exception as e:
        print(f"Query failed: {query} - {e}", file=sys.stderr)
    return []


def query_range_increase(prom_url: str, metric: str, start: datetime, end: datetime, use_sum: bool = True) -> float | None:
    """Query the increase of a counter over a time range, summed across all series."""
    duration = int((end - start).total_seconds())
    if use_sum:
        query = f"sum(increase({metric}[{duration}s]))"
    else:
        query = f"increase({metric}[{duration}s])"
    return query_prometheus(prom_url, query, end)


def query_range_increase_by_label(
    prom_url: str, metric: str, start: datetime, end: datetime, group_by: str
) -> list[tuple[str, float]]:
    """Query increase of a counter grouped by label."""
    duration = int((end - start).total_seconds())
    query = f"sum by({group_by}) (increase({metric}[{duration}s]))"
    results = query_prometheus_vector(prom_url, query, end)
    return [(m.get(group_by, "unknown"), v) for m, v in results if v > 0]


def query_avg_latency(prom_url: str, start: datetime, end: datetime) -> float | None:
    """Query average request latency over time range."""
    duration = int((end - start).total_seconds())
    # Average of the rate of sum / rate of count
    query = f"""
        sum(increase(vllm:e2e_request_latency_seconds_sum[{duration}s]))
        /
        sum(increase(vllm:e2e_request_latency_seconds_count[{duration}s]))
    """.strip()
    return query_prometheus(prom_url, query, end)


def format_number(n: float | None, decimals: int = 0) -> str:
    """Format number with thousands separator."""
    if n is None:
        return "N/A"
    if decimals == 0:
        return f"{int(n):,}"
    return f"{n:,.{decimals}f}"


def query_active_users(prom_url: str, time: datetime) -> float | None:
    """Query active users, trying multiple metric name formats."""
    # Try different metric name formats (OTEL may convert colons to underscores)
    for metric in ["openwebui_users_active_30d", "openwebui:users_active_30d"]:
        result = query_prometheus(prom_url, metric, time)
        if result is not None:
            return result
    # Fallback: count unique users with messages
    result = query_prometheus(prom_url, "count(openwebui_user_messages > 0)", time)
    return result


def generate_report(prom_url: str, start: datetime, end: datetime):
    """Generate and print the KPI report."""
    # Fetch metrics
    active_users = query_active_users(prom_url, end)
    total_tokens = query_range_increase(prom_url, "vllm:generation_tokens_total", start, end)
    avg_latency = query_avg_latency(prom_url, start, end)
    tokens_by_model = query_range_increase_by_label(
        prom_url, "vllm:generation_tokens_total", start, end, "model_name"
    )

    # Sort models by token count descending
    tokens_by_model.sort(key=lambda x: x[1], reverse=True)

    # Calculate percentages
    total_model_tokens = sum(t[1] for t in tokens_by_model) if tokens_by_model else 0

    # Format dates
    start_str = start.strftime("%Y-%m-%d")
    end_str = end.strftime("%Y-%m-%d")

    # Print report
    print()
    print("=" * 60)
    print(f"KPI REPORT: {start_str} to {end_str}")
    print("=" * 60)
    print()
    print("KEY METRICS:")
    print(f"  Active Users:              {format_number(active_users):>12}")
    print(f"  Total Tokens Generated:    {format_number(total_tokens):>12}")
    if avg_latency is not None:
        print(f"  Avg Response Time:         {avg_latency:>11.3f}s")
    else:
        print(f"  Avg Response Time:         {'N/A':>12}")
    print()

    if tokens_by_model:
        print("TOKENS BY MODEL:")
        for model, tokens in tokens_by_model:
            pct = (tokens / total_model_tokens * 100) if total_model_tokens > 0 else 0
            # Truncate model name if too long
            display_model = model if len(model) <= 40 else model[:37] + "..."
            print(f"  {display_model:<42} {format_number(tokens):>10} ({pct:5.1f}%)")
    else:
        print("TOKENS BY MODEL:")
        print("  No data available")

    print()
    print("=" * 60)

def main():
    args = parse_args()
    start, end = get_date_range(args)

    print(f"Generating KPI report for {start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}...")
    print(f"Prometheus: {args.prometheus}")

    generate_report(args.prometheus, start, end)


if __name__ == "__main__":
    main()
