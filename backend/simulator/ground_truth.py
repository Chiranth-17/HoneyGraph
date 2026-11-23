"""Ground-truth benchmark labels, stored separately from observed events."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def label(
    scenario_id: str,
    scenario: str,
    stage: str,
    actor: str,
    target: str | list[str],
    start: datetime,
    end: datetime,
    event_count: int,
) -> dict[str, Any]:
    return {
        "scenarioId": scenario_id,
        "scenario": scenario,
        "stage": stage,
        "actor": actor,
        "target": target,
        "eventTimeRange": {"start": start, "end": end},
        "eventCount": event_count,
    }

