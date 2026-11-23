"""Generate tamper indicators; the runner performs scoped demo mutations."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId
from pymongo.database import Database

from ..ground_truth import label
from ..models import EventFactory
from .common import ScenarioOutput


def generate(devices: list[dict[str, Any]], attackers: list[str], seed: int, start: datetime, factory: EventFactory) -> ScenarioOutput:
    target = random.Random(seed).choice(devices)
    actor = attackers[4]
    events = [
        factory.make(target, start, "http", "tamper_update_attempt", actor, {"method": "PATCH", "path": "/logs", "username": "demo", "status": 403}),
        factory.make(target, start + timedelta(milliseconds=250), "http", "tamper_delete_attempt", actor, {"method": "DELETE", "path": "/logs", "username": "demo", "status": 403}),
    ]
    return ScenarioOutput(events, [label(f"tamper-{seed}", "log_tamper", "defense-evasion", actor, target["deviceId"], events[0]["ts"], events[-1]["ts"], len(events))])


def perform_demo(db: Database[Any], event_ids: list[ObjectId]) -> dict[str, int]:
    """Update and delete only IDs selected by the trusted simulator runner."""
    if len(event_ids) < 2:
        return {"updated": 0, "deleted": 0}
    updated = db.events.update_one({"_id": event_ids[0]}, {"$set": {"eventType": "tampered_demo"}}).modified_count
    deleted = db.events.delete_one({"_id": event_ids[1]}).deleted_count
    return {"updated": updated, "deleted": deleted}

