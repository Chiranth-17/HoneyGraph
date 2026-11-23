"""CLI orchestration for deterministic HoneyGraph simulations."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pymongo import MongoClient

from .devices import attacker_ips, generate_devices, upsert_devices
from .models import EventFactory
from .normal_traffic import generate_normal_traffic
from .scenarios import SCENARIOS
from .scenarios.log_tamper import perform_demo
from .sinks import ApiSink, DirectMongoSink, EventSink, service_uri

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DEFAULT_START = datetime(2026, 10, 14, tzinfo=timezone.utc)


def select_scenarios(value: str) -> list[str]:
    names = list(SCENARIOS) if value == "all" else [item.strip() for item in value.split(",") if item.strip()]
    unknown = sorted(set(names) - set(SCENARIOS))
    if unknown:
        raise ValueError(f"unknown scenarios: {', '.join(unknown)}")
    return names


def generate(
    device_count: int,
    rate: int,
    duration: int,
    scenario_names: list[str],
    seed: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    """Pure deterministic generation used by both CLI and tests."""
    devices = generate_devices(device_count, seed)
    attackers = attacker_ips(8, seed + 1)
    factory = EventFactory()
    normal = generate_normal_traffic(devices, rate, duration, seed + 2, DEFAULT_START, factory)
    events = list(normal)
    labels: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    scenario_start = DEFAULT_START + timedelta(seconds=duration + 1)
    for index, name in enumerate(scenario_names):
        output = SCENARIOS[name](devices, attackers, seed + index * 101, scenario_start + timedelta(seconds=index * 10), factory)
        events.extend(output.events)
        labels.extend(output.labels)
        counts[name] = len(output.events)
    return devices, events, labels, counts


def persist(
    devices: list[dict[str, Any]],
    events: list[dict[str, Any]],
    labels: list[dict[str, Any]],
    sink: EventSink,
    tamper_enabled: bool,
) -> list[Any]:
    """Persist inventory/labels as admin and observations through the chosen sink."""
    with MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=10_000) as admin:
        db = admin[os.getenv("MONGO_DATABASE", "honeygraph")]
        upsert_devices(db, devices)
        if labels:
            db.ground_truth.insert_many(labels)
    identifiers = sink.write(events)
    if tamper_enabled and len(identifiers) >= 2:
        with MongoClient(service_uri("tamper_demo", os.environ["MONGO_TAMPER_PASSWORD"])) as tamper:
            perform_demo(tamper[os.getenv("MONGO_DATABASE", "honeygraph")], identifiers[:2])
    return identifiers


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate safe synthetic IoT traffic for HoneyGraph")
    parser.add_argument("--devices", type=int, default=500)
    parser.add_argument("--rate", type=int, default=2_000, help="normal events per logical second")
    parser.add_argument("--duration", type=int, default=60, help="logical seconds")
    parser.add_argument("--scenarios", default="all", help="all or comma-separated scenario names")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sink", choices=("direct", "api"), default="api")
    parser.add_argument("--api-url", default=f"http://localhost:{os.getenv('BACKEND_PORT', '8000')}")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    names = select_scenarios(args.scenarios)
    devices, events, labels, scenario_counts = generate(args.devices, args.rate, args.duration, names, args.seed)
    sink: EventSink = DirectMongoSink() if args.sink == "direct" else ApiSink(args.api_url)
    try:
        persist(devices, events, labels, sink, "log_tamper" in names)
    finally:
        close = getattr(sink, "close", None)
        if close:
            close()
    summary = {
        "devices": len(devices),
        "eventsAttempted": len(events),
        "eventsStoredAfterTamper": len(events) - (1 if "log_tamper" in names and len(events) >= 2 else 0),
        "protocols": dict(sorted(Counter(event["protocol"] for event in events).items())),
        "scenarios": scenario_counts,
        "groundTruthLabels": len(labels),
        "seed": args.seed,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

