"""Shared settings and validation for the Task 2 streaming steps."""

import datetime as dt
import json
import os
import shutil
import subprocess
from pathlib import Path

def _gcloud_project() -> str:
    """The project currently set in gcloud (`gcloud config get-value project`)."""
    gcloud = shutil.which("gcloud")
    if not gcloud:
        return ""
    result = subprocess.run([gcloud, "config", "get-value", "project"], capture_output=True, text=True)
    return result.stdout.strip()


PROJECT = os.environ.get("GCP_PROJECT") or _gcloud_project()
DATASET = "retail_case"
TOPIC = "ga4-events"
SUBSCRIPTION = "ga4-events-consumer"

DATA_DIR = Path(__file__).resolve().parents[1] / "data"

REQUIRED = {"event_id": str, "event_timestamp": int, "event_name": str, "user_pseudo_id": str}
GA4_FIELDS = ["event_id", "event_date", "event_timestamp", "event_name", "user_pseudo_id",
              "user_id", "event_params", "user_properties", "items"]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def validate(raw: bytes) -> tuple[dict | None, list[str]]:
    """Return (event, []) when valid, otherwise (None, reasons)."""
    try:
        event = json.loads(raw)
    except ValueError as exc:
        return None, [f"invalid json: {exc}"]
    if not isinstance(event, dict):
        return None, ["payload is not a JSON object"]

    errors = []
    for field, expected_type in REQUIRED.items():
        value = event.get(field)
        if value is None or value == "":
            errors.append(f"missing {field}")
        elif not isinstance(value, expected_type) or isinstance(value, bool):
            errors.append(f"{field} must be {expected_type.__name__}")
    return (None, errors) if errors else (event, [])


def to_row(event: dict) -> dict:
    """Keep only schema columns (unknown keys would fail the BigQuery insert) and add event time."""
    row = {field: event.get(field) for field in GA4_FIELDS}
    for field in ("event_params", "user_properties", "items"):
        row[field] = row[field] or []
    epoch = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
    row["event_ts"] = (epoch + dt.timedelta(microseconds=event["event_timestamp"])).isoformat()
    row["ingested_at"] = utc_now()
    return row
