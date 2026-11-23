"""Abstract Mirai-like scan and credential sequence; no exploit behavior."""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import Any

from ..ground_truth import label
from ..models import EventFactory
from .common import ScenarioOutput


def generate(devices: list[dict[str, Any]], attackers: list[str], seed: int, start: datetime, factory: EventFactory) -> ScenarioOutput:
    rng = random.Random(seed)
    targets = rng.sample(devices, min(4, len(devices)))
    actor = attackers[0]
    events: list[dict[str, Any]] = []
    step = 0
    for target in targets:
        events.append(factory.make(target, start + timedelta(milliseconds=step * 100), "telnet", "scan", actor, {"user": "probe", "attempts": 0}))
        step += 1
    victim = targets[0]
    for attempt in range(12):
        events.append(factory.make(victim, start + timedelta(milliseconds=step * 100), "telnet", "login_failed", actor, {"user": rng.choice(["root", "admin", "guest"]), "attempts": attempt + 1}))
        step += 1
    for event_type in ("login_success", "command_exec"):
        events.append(factory.make(victim, start + timedelta(milliseconds=step * 100), "telnet", event_type, actor, {"user": "admin", "attempts": 13}))
        step += 1
    scenario_id = f"mirai-{seed}"
    return ScenarioOutput(events, [label(scenario_id, "mirai_bruteforce", "credential-access", actor, victim["deviceId"], events[0]["ts"], events[-1]["ts"], len(events))])

