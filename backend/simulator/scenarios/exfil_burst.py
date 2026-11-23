"""Generate bytesOut far above the selected device's normal baseline."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

from ..ground_truth import label
from ..models import EventFactory
from .common import ScenarioOutput


def generate(devices: list[dict[str, Any]], attackers: list[str], seed: int, start: datetime, factory: EventFactory) -> ScenarioOutput:
    target = random.Random(seed).choice(devices)
    baseline = target["baseline"]["bytesOut"]
    events = [factory.make(target, start + timedelta(milliseconds=i * 250), target["protocol"], "exfil_burst", target["ip"], {"bytesOut": baseline * (20 + i), "bytesIn": 100}) for i in range(5)]
    return ScenarioOutput(events, [label(f"exfil-{seed}", "exfil_burst", "exfiltration", target["ip"], target["deviceId"], events[0]["ts"], events[-1]["ts"], len(events))])

