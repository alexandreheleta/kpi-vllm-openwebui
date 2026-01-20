#!/usr/bin/env python3
"""
Open WebUI Metrics Exporter

Exports user activity metrics from Open WebUI's SQLite database via OpenTelemetry.
Designed for the Executive KPI dashboard - provides only essential metrics.
"""

import json
import os
import sqlite3
import time

from opentelemetry import metrics
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

# Configuration
DB_PATH = os.environ.get("WEBUI_DB_PATH", "/data/webui.db")
OTLP_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-backend:4317")
EXPORT_INTERVAL = int(os.environ.get("EXPORT_INTERVAL", "15"))


class MetricsCollector:
    """Collects metrics from Open WebUI SQLite database."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection | None:
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            return None

    def _count_assistant_messages(self, chat_json: str) -> int:
        """Count assistant messages in a chat JSON blob."""
        try:
            data = json.loads(chat_json) if chat_json else {}
            return sum(1 for m in data.get("messages", []) if m.get("role") == "assistant")
        except (json.JSONDecodeError, TypeError):
            return 0

    def _extract_models(self, chat_json: str) -> list[str]:
        """Extract model names from a chat JSON blob."""
        try:
            data = json.loads(chat_json) if chat_json else {}
            return data.get("models", [])
        except (json.JSONDecodeError, TypeError):
            return []

    def collect_all(self) -> dict:
        """Collect all metrics in a single database query."""
        result = {
            "users_total": 0,
            "users_active_30d": 0,
            "chats_total": 0,
            "messages_total": 0,
            "model_usage": {},
            "user_messages": {},
        }

        conn = self._get_connection()
        if not conn:
            return result

        try:
            cursor = conn.cursor()

            # User metrics (single query)
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN last_active_at > unixepoch() - 2592000 THEN 1 ELSE 0 END) as active_30d
                FROM user
            """)
            row = cursor.fetchone()
            result["users_total"] = row["total"]
            result["users_active_30d"] = row["active_30d"] or 0

            # Chat count
            cursor.execute("SELECT COUNT(*) as total FROM chat")
            result["chats_total"] = cursor.fetchone()["total"]

            # User names lookup
            cursor.execute("SELECT id, name FROM user")
            user_names = {r["id"]: r["name"] or "Unknown" for r in cursor.fetchall()}

            # Process chats for messages, models, and per-user counts
            cursor.execute("SELECT user_id, chat FROM chat")
            for row in cursor.fetchall():
                try:
                    user_id = row["user_id"]
                    chat_json = row["chat"]
                    msg_count = self._count_assistant_messages(chat_json)

                    result["messages_total"] += msg_count

                    # Per-user message count
                    user_name = user_names.get(user_id, "Unknown")
                    result["user_messages"][user_name] = result["user_messages"].get(user_name, 0) + msg_count

                    # Per-model usage
                    for model in self._extract_models(chat_json):
                        result["model_usage"][model] = result["model_usage"].get(model, 0) + msg_count
                except Exception as e:
                    print(f"Skipping corrupt chat row: {e}")

        finally:
            conn.close()

        return result


def create_callbacks(collector: MetricsCollector, export_interval: int):
    """Create OTEL metric callbacks."""
    cached_data = {"value": None, "timestamp": 0}
    cache_ttl = max(5, export_interval - 5)  # Expire slightly before next export

    def get_cached_data():
        now = time.time()
        if cached_data["value"] is None or (now - cached_data["timestamp"]) > cache_ttl:
            cached_data["value"] = collector.collect_all()
            cached_data["timestamp"] = now
        return cached_data["value"]

    def users_total_callback(_):
        yield metrics.Observation(get_cached_data()["users_total"])

    def users_active_30d_callback(_):
        yield metrics.Observation(get_cached_data()["users_active_30d"])

    def chats_total_callback(_):
        yield metrics.Observation(get_cached_data()["chats_total"])

    def messages_total_callback(_):
        yield metrics.Observation(get_cached_data()["messages_total"])

    def model_usage_callback(_):
        for model, count in get_cached_data()["model_usage"].items():
            yield metrics.Observation(count, {"model": model})

    def user_messages_callback(_):
        for user, count in get_cached_data()["user_messages"].items():
            yield metrics.Observation(count, {"user_name": user})

    return {
        "users_total": users_total_callback,
        "users_active_30d": users_active_30d_callback,
        "chats_total": chats_total_callback,
        "messages_total": messages_total_callback,
        "model_usage": model_usage_callback,
        "user_messages": user_messages_callback,
    }


def main():
    print(f"Open WebUI Metrics Exporter")
    print(f"  Database: {DB_PATH}")
    print(f"  OTLP Endpoint: {OTLP_ENDPOINT}")
    print(f"  Export Interval: {EXPORT_INTERVAL}s")

    # Wait for database
    while not os.path.exists(DB_PATH):
        print("Waiting for database...")
        time.sleep(5)

    # Setup OpenTelemetry
    resource = Resource.create({"service.name": "openwebui-exporter"})
    exporter = OTLPMetricExporter(endpoint=OTLP_ENDPOINT, insecure=True)
    reader = PeriodicExportingMetricReader(exporter, export_interval_millis=EXPORT_INTERVAL * 1000)
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    metrics.set_meter_provider(provider)

    meter = metrics.get_meter("openwebui.metrics")
    collector = MetricsCollector(DB_PATH)
    callbacks = create_callbacks(collector, EXPORT_INTERVAL)

    # Register metrics
    meter.create_observable_gauge(
        "openwebui_users_total",
        callbacks=[callbacks["users_total"]],
        description="Total registered users",
    )
    meter.create_observable_gauge(
        "openwebui_users_active_30d",
        callbacks=[callbacks["users_active_30d"]],
        description="Users active in last 30 days",
    )
    meter.create_observable_gauge(
        "openwebui_chats_total",
        callbacks=[callbacks["chats_total"]],
        description="Total chat sessions",
    )
    meter.create_observable_gauge(
        "openwebui_messages_total",
        callbacks=[callbacks["messages_total"]],
        description="Total AI responses",
    )
    meter.create_observable_gauge(
        "openwebui_model_usage",
        callbacks=[callbacks["model_usage"]],
        description="AI responses per model",
    )
    meter.create_observable_gauge(
        "openwebui_user_messages",
        callbacks=[callbacks["user_messages"]],
        description="AI responses per user",
    )

    print("Exporter running. Metrics: users_total, users_active_30d, chats_total, messages_total, model_usage, user_messages")

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("Shutting down...")
        provider.shutdown()


if __name__ == "__main__":
    main()
