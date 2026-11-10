"""Turn a raw incident bundle into a compact, LLM-friendly context.

The main idea: a real incident can produce thousands of near-identical log lines.
Sending them all wastes tokens and buries the signal, so we normalise volatile
tokens (timestamps, IDs, IPs, numbers), group identical patterns and keep counts.
"""
from __future__ import annotations

import json
import re
from collections import OrderedDict
from datetime import datetime
from typing import Any

# Order matters: timestamps first, bare numbers last.
_NORMALIZERS = [
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?"), "<ts>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "<uuid>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b"), "<ip>"),
    (re.compile(r"\b0x[0-9a-f]+\b", re.I), "<hex>"),
    # Kubernetes pod suffix such as -7d9f8b6c5d-x2k4p (first group must contain a digit)
    (re.compile(r"-(?=[a-z0-9]*\d)[a-z0-9]{5,10}-[a-z0-9]{5}\b"), "-<pod>"),
    # Bare numbers, including ones glued to units (3002ms), but not digits inside identifiers (x2k4p)
    (re.compile(r"(?<![A-Za-z_])\d+(?:\.\d+)?"), "<n>"),
]


def normalize(line: str) -> str:
    """Replace volatile tokens so repeated messages collapse to one pattern."""
    for pattern, repl in _NORMALIZERS:
        line = pattern.sub(repl, line)
    return line.strip()


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def cluster_logs(logs: list[Any], max_clusters: int = 15) -> list[dict]:
    """Group log entries by normalised message; most frequent first.

    Each entry may be a plain string or a dict with 'message', 'level', 'time'.
    """
    clusters: "OrderedDict[str, dict]" = OrderedDict()
    for entry in logs:
        if isinstance(entry, str):
            message, level, ts = entry, "", None
        else:
            message = entry.get("message", "")
            level = entry.get("level", "")
            ts = entry.get("time")
        key = normalize(f"{level} {message}".strip())
        c = clusters.setdefault(
            key, {"pattern": key, "count": 0, "example": message, "first_seen": ts, "last_seen": ts}
        )
        c["count"] += 1
        if ts:
            c["first_seen"] = c["first_seen"] or ts
            c["last_seen"] = ts
    ranked = sorted(clusters.values(), key=lambda c: c["count"], reverse=True)
    return ranked[:max_clusters]


def build_timeline(alerts: list[dict], events: list[dict]) -> list[dict]:
    """Merge alerts and Kubernetes events into one chronological list."""
    items: list[dict] = []
    for a in alerts:
        label = f"[{a.get('severity', 'n/a')}] {a.get('name', 'alert')}: {a.get('summary', '')}".strip()
        items.append({"time": a.get("starts_at"), "source": "alert", "text": label})
        if a.get("resolved_at"):
            items.append({"time": a["resolved_at"], "source": "alert", "text": f"RESOLVED {a.get('name', 'alert')}"})
    for e in events:
        text = f"{e.get('type', '')} {e.get('reason', '')} on {e.get('object', '?')}: {e.get('message', '')}".strip()
        items.append({"time": e.get("time"), "source": "k8s", "text": text})

    far_future = datetime.max.replace(tzinfo=None)

    def sort_key(item: dict):
        dt = parse_ts(item["time"])
        # Entries with unparseable timestamps sort last, stable otherwise.
        return (dt is None, dt.replace(tzinfo=None) if dt else far_future)

    return sorted(items, key=sort_key)


def load_bundle(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def build_context(bundle: dict, max_log_clusters: int = 15) -> dict:
    """Build the compact context handed to the LLM (and to the offline heuristic)."""
    alerts = bundle.get("alerts", [])
    events = bundle.get("k8s_events", [])
    logs = bundle.get("logs", [])
    return {
        "service": bundle.get("service", "unknown"),
        "environment": bundle.get("environment", "unknown"),
        "window": bundle.get("window", {}),
        "timeline": build_timeline(alerts, events),
        "log_clusters": cluster_logs(logs, max_log_clusters),
        "raw_counts": {"alerts": len(alerts), "k8s_events": len(events), "log_lines": len(logs)},
    }
