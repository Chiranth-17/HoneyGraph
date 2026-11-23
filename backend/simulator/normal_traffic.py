"""Configurable deterministic normal-traffic generator."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

from .models import EventFactory

TRAFFIC_KINDS = ("mqtt", "coap", "http", "ssh", "telemetry")


def _payload(kind: str, device: dict[str, Any], rng: random.Random) -> tuple[str, str, dict[str, Any]]:
    if kind == "mqtt":
        return "mqtt", "mqtt_publish", {"topic": f"sensors/{device['deviceId']}", "clientId": device["deviceId"], "action": "publish"}
    if kind == "coap":
        return "coap", "coap_read", {"uri": "/metrics", "code": "2.05"}
    if kind == "http":
        return "http", "http_request", {"method": "GET", "path": "/health", "username": "device", "status": 200}
    if kind == "ssh":
        return "ssh", "session_ok", {"user": "maint", "attempts": 1}
    baseline = device["baseline"]["bytesOut"]
    return device["protocol"], "telemetry", {
        "bytesOut": max(0, baseline + rng.randint(-baseline // 5, baseline // 5)),
        "bytesIn": rng.randint(250, 3_000),
    }


def generate_normal_traffic(
    devices: list[dict[str, Any]],
    rate: int,
    duration: int,
    seed: int,
    start: datetime,
    factory: EventFactory | None = None,
) -> list[dict[str, Any]]:
    """Generate ``rate * duration`` events spread across logical time."""
    if rate < 0 or duration < 0:
        raise ValueError("rate and duration must be non-negative")
    if not devices and rate * duration:
        raise ValueError("at least one device is required")
    rng = random.Random(seed)
    builder = factory or EventFactory()
    total = rate * duration
    events: list[dict[str, Any]] = []
    for index in range(total):
        device = devices[rng.randrange(len(devices))]
        kind = TRAFFIC_KINDS[index % len(TRAFFIC_KINDS)]
        protocol, event_type, payload = _payload(kind, device, rng)
        offset = (index / rate) if rate else 0
        events.append(builder.make(device, start + timedelta(seconds=offset), protocol, event_type, device["ip"], payload))
    return events

