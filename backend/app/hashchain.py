"""Canonical per-device SHA-256 event hash-chain functions."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

GENESIS_HASH = "0" * 64
CANONICAL_FIELDS = ("ts", "deviceId", "protocol", "eventType", "srcIp", "geo", "payload")


def utc_timestamp(value: datetime) -> datetime:
    """Normalize a timestamp; BSON-naive values are defined to be UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    normalized = value.astimezone(timezone.utc)
    return normalized.replace(microsecond=(normalized.microsecond // 1_000) * 1_000)


def canonical_form(event: dict[str, Any]) -> bytes:
    """Return sorted, whitespace-free UTF-8 JSON with fixed timestamp precision."""
    body = {field: event[field] for field in CANONICAL_FIELDS}
    body["ts"] = utc_timestamp(body["ts"]).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def compute_hash(previous_hash: str, event: dict[str, Any]) -> str:
    if len(previous_hash) != 64:
        raise ValueError("previous hash must contain 64 hexadecimal characters")
    return hashlib.sha256(previous_hash.encode("ascii") + canonical_form(event)).hexdigest()


def verify_link(event: dict[str, Any], expected_previous: str) -> bool:
    return event.get("prevHash") == expected_previous and event.get("hash") == compute_hash(expected_previous, event)

