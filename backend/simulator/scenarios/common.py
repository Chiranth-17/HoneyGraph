"""Types and helpers shared by scenario generators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScenarioOutput:
    events: list[dict[str, Any]]
    labels: list[dict[str, Any]]

