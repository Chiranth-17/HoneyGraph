"""Shared event construction and hash-chain primitives."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.hashchain import GENESIS_HASH as ZERO_HASH
from app.hashchain import canonical_form as canonical_event
from app.hashchain import compute_hash as chained_hash


class EventFactory:
    """Build schema-valid events while maintaining a per-device hash chain."""

    def __init__(self) -> None:
        self._heads: dict[str, str] = {}

    def make(
        self,
        device: dict[str, Any],
        ts: datetime,
        protocol: str,
        event_type: str,
        src_ip: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        event = {
            "ts": ts,
            "deviceId": device["deviceId"],
            "protocol": protocol,
            "eventType": event_type,
            "srcIp": src_ip,
            "geo": device["location"],
            "payload": payload,
        }
        previous = self._heads.get(device["deviceId"], ZERO_HASH)
        event["prevHash"] = previous
        event["hash"] = chained_hash(previous, event)
        self._heads[device["deviceId"]] = event["hash"]
        return event

