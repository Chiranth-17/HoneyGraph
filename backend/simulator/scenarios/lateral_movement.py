"""A compromised camera becomes the synthetic source for a 2-4 hop chain."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

from ..ground_truth import label
from ..models import EventFactory
from .common import ScenarioOutput


def generate(devices: list[dict[str, Any]], attackers: list[str], seed: int, start: datetime, factory: EventFactory) -> ScenarioOutput:
    rng = random.Random(seed)
    cameras = [device for device in devices if device["type"] == "camera"] or devices
    origin = rng.choice(cameras)
    candidates = [device for device in devices if device["deviceId"] != origin["deviceId"]]
    hops = rng.sample(candidates, min(rng.randint(2, 4), len(candidates)))
    events: list[dict[str, Any]] = []
    source = origin
    for index, target in enumerate(hops):
        events.append(factory.make(target, start + timedelta(milliseconds=index * 300), "ssh", "lateral_login", source["ip"], {"user": "service", "attempts": 1}))
        source = target
    return ScenarioOutput(events, [label(f"lateral-{seed}", "lateral_movement", "lateral-movement", origin["ip"], [d["deviceId"] for d in hops], events[0]["ts"], events[-1]["ts"], len(events))])

