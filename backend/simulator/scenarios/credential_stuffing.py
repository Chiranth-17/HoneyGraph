"""HTTP login attempts with many distinct synthetic usernames."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

from ..ground_truth import label
from ..models import EventFactory
from .common import ScenarioOutput


def generate(devices: list[dict[str, Any]], attackers: list[str], seed: int, start: datetime, factory: EventFactory) -> ScenarioOutput:
    target = random.Random(seed).choice(devices)
    actor = attackers[2]
    events = [factory.make(target, start + timedelta(milliseconds=i * 120), "http", "login_failed", actor, {"method": "POST", "path": "/login", "username": f"user{i:03d}", "status": 401}) for i in range(20)]
    return ScenarioOutput(events, [label(f"stuffing-{seed}", "credential_stuffing", "credential-access", actor, target["deviceId"], events[0]["ts"], events[-1]["ts"], len(events))])

