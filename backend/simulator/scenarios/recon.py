"""One documentation-range source touches many devices and logical ports."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

from ..ground_truth import label
from ..models import EventFactory
from .common import ScenarioOutput


def generate(devices: list[dict[str, Any]], attackers: list[str], seed: int, start: datetime, factory: EventFactory) -> ScenarioOutput:
    rng = random.Random(seed)
    targets = rng.sample(devices, min(30, len(devices)))
    actor = attackers[1]
    ports = (22, 23, 80, 1883, 5683)
    events = [factory.make(target, start + timedelta(milliseconds=i * 80), "ssh", "port_scan", actor, {"user": f"port-{ports[i % len(ports)]}", "attempts": 0}) for i, target in enumerate(targets)]
    return ScenarioOutput(events, [label(f"recon-{seed}", "recon", "discovery", actor, [d["deviceId"] for d in targets], events[0]["ts"], events[-1]["ts"], len(events))])

