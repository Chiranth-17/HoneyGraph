"""Optional mapping from Cowrie JSON-lines records to HoneyGraph events."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import EventFactory


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc)


def map_record(record: dict[str, Any], device: dict[str, Any], factory: EventFactory) -> dict[str, Any] | None:
    """Map login and command Cowrie records without replaying any commands."""
    event_id = record.get("eventid", "")
    mapping = {
        "cowrie.login.failed": "login_failed",
        "cowrie.login.success": "login_success",
        "cowrie.command.input": "command_exec",
    }
    event_type = mapping.get(event_id)
    if event_type is None:
        return None
    return factory.make(
        device,
        _timestamp(record["timestamp"]),
        "ssh",
        event_type,
        record.get("src_ip", "192.0.2.1"),
        {"user": record.get("username", "unknown"), "attempts": 1},
    )


def import_json_lines(path: Path, device: dict[str, Any], factory: EventFactory | None = None) -> list[dict[str, Any]]:
    builder = factory or EventFactory()
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        mapped = map_record(json.loads(line), device, builder)
        if mapped:
            events.append(mapped)
    return events

