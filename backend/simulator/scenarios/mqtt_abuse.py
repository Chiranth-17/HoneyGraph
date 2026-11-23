"""Synthetic unauthorized publish to restricted control topics."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

from ..ground_truth import label
from ..models import EventFactory
from .common import ScenarioOutput


def generate(devices: list[dict[str, Any]], attackers: list[str], seed: int, start: datetime, factory: EventFactory) -> ScenarioOutput:
    target = random.Random(seed).choice(devices)
    actor = attackers[3]
    topics = ("control/signals/override", "control/grid/shed", "control/cameras/disable")
    events = [factory.make(target, start + timedelta(milliseconds=i * 200), "mqtt", "restricted_publish", actor, {"topic": topic, "clientId": f"unlisted-{seed}", "action": "publish"}) for i, topic in enumerate(topics)]
    return ScenarioOutput(events, [label(f"mqtt-{seed}", "mqtt_abuse", "impact", actor, target["deviceId"], events[0]["ts"], events[-1]["ts"], len(events))])

