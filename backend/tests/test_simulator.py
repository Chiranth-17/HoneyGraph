"""Phase 2 integration tests for deterministic, schema-valid simulation."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from pymongo import MongoClient

from simulator.cowrie_import import import_json_lines
from simulator.devices import generate_devices
from simulator.models import EventFactory
from simulator.run import generate
from simulator.scenarios import SCENARIOS

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DB_NAME = os.getenv("MONGO_DATABASE", "honeygraph")


@pytest.fixture(scope="module")
def root_client() -> MongoClient:
    client = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=5_000)
    client.admin.command("ping")
    yield client
    client.close()


def test_same_seed_produces_identical_output() -> None:
    names = list(SCENARIOS)
    first = generate(40, 3, 2, names, 42)
    second = generate(40, 3, 2, names, 42)
    assert first == second
    assert first != generate(40, 3, 2, names, 43)


def test_every_generated_event_passes_database_schema(root_client: MongoClient) -> None:
    _, events, _, _ = generate(50, 2, 2, list(SCENARIOS), 104)
    collection = root_client[DB_NAME].events
    result = collection.insert_many(events)
    try:
        assert len(result.inserted_ids) == len(events)
    finally:
        collection.delete_many({"_id": {"$in": result.inserted_ids}})


def test_ground_truth_record_exists_for_every_scenario(root_client: MongoClient) -> None:
    _, _, labels, _ = generate(50, 1, 1, list(SCENARIOS), 205)
    collection = root_client[DB_NAME].ground_truth
    result = collection.insert_many(labels)
    try:
        found = {item["scenario"] for item in collection.find({"_id": {"$in": result.inserted_ids}})}
        assert found == set(SCENARIOS)
        for item in labels:
            assert {"scenarioId", "stage", "actor", "target", "eventTimeRange"} <= item.keys()
    finally:
        collection.delete_many({"_id": {"$in": result.inserted_ids}})


def test_device_inventory_uses_private_addresses_and_bengaluru_points() -> None:
    devices = generate_devices(500, 42)
    assert len({item["deviceId"] for item in devices}) == 500
    assert all(item["ip"].startswith("10.42.") for item in devices)
    assert all(77.40 < item["location"]["coordinates"][0] < 77.79 for item in devices)
    assert all(12.82 < item["location"]["coordinates"][1] < 13.12 for item in devices)


def test_cowrie_sample_maps_to_schema_events() -> None:
    device = generate_devices(1, 7)[0]
    path = ROOT / "backend" / "simulator" / "samples" / "cowrie.jsonl"
    events = import_json_lines(path, device, EventFactory())
    assert [event["eventType"] for event in events] == ["login_failed", "login_success", "command_exec"]
    assert all(event["protocol"] == "ssh" for event in events)
