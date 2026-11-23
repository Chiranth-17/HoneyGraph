"""Phase 5 graph, transaction, risk, and rollup integration tests."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

from workers.chain_builder import ChainBuilder
from workers.risk_scorer import calculate_risks
from workers.telemetry_rollup import rollup_minute

load_dotenv()


@pytest.fixture()
def database():
    with MongoClient(os.environ["MONGODB_URI"]) as client:
        db = client[os.getenv("MONGO_DATABASE", "honeygraph")]
        yield client, db


def alert(device: str, actor: str, target: str, ts: datetime, severity: int = 8) -> dict:
    return {
        "ts": ts, "ruleId": "R-LATERAL-06", "deviceId": device, "actor": actor,
        "targetIp": target, "stage": "lateral-movement", "severity": severity,
        "eventIds": [ObjectId()], "eventInsertedAt": ts, "alertCreatedAt": ts,
        "dedupeKey": str(ObjectId()),
    }


def test_chain_order_idempotency_and_cycle_guard(database):
    client, db = database
    now = datetime.now(timezone.utc).replace(microsecond=0)
    docs = [alert("p5-a", "192.0.2.1", "10.0.0.1", now), alert("p5-b", "10.0.0.1", "10.0.0.2", now + timedelta(seconds=1)), alert("p5-c", "10.0.0.2", "10.0.0.3", now + timedelta(seconds=2))]
    ids = db.alerts.insert_many(docs).inserted_ids
    builder = ChainBuilder(client, db.name)
    try:
        first = builder.build(ids[-1])
        second = builder.build(ids[1])
        incident = db.incidents.find_one({"_id": first})
        assert first == second
        assert [node["hop"] for node in incident["chain"]] == [0, 1, 2]
        assert len({node["alertId"] for node in incident["chain"]}) == 3
        assert db.incidents.count_documents({"chainKey": incident["chainKey"]}) == 1
    finally:
        db.alerts.delete_many({"_id": {"$in": ids}})
        db.incidents.delete_many({"_id": first} if "first" in locals() else {"chainKey": {"$exists": True}})
        db.risk_scores.delete_many({"deviceId": {"$in": ["p5-a", "p5-b", "p5-c"]}})


def test_forced_failure_aborts_every_write(database):
    client, db = database
    now = datetime.now(timezone.utc).replace(microsecond=0)
    doc = alert("p5-rollback", "198.51.100.1", "10.9.0.1", now)
    alert_id = db.alerts.insert_one(doc).inserted_id
    try:
        with pytest.raises(RuntimeError, match="forced"):
            ChainBuilder(client, db.name).build(alert_id, lambda: (_ for _ in ()).throw(RuntimeError("forced")))
        assert db.alerts.find_one({"_id": alert_id, "incidentId": {"$exists": True}}) is None
        assert db.incidents.count_documents({"chain.0.alertId": alert_id}) == 0
        assert db.risk_scores.find_one({"deviceId": "p5-rollback"}) is None
    finally:
        db.alerts.delete_one({"_id": alert_id})


def test_risk_decays_and_is_capped(database):
    _, db = database
    now = datetime.now(timezone.utc).replace(microsecond=0)
    ids = db.alerts.insert_many([alert("p5-risk", "203.0.113.1", "10.8.0.1", now, 10) for _ in range(12)]).inserted_ids
    try:
        fresh = calculate_risks(db, ["p5-risk"], as_of=now, half_life_hours=6)[0]
        aged = calculate_risks(db, ["p5-risk"], as_of=now + timedelta(hours=6), half_life_hours=6)[0]
        assert fresh["score"] == 100
        assert aged["score"] == pytest.approx(60, rel=0.02)
        assert len(fresh["factors"]) == 5
    finally:
        db.alerts.delete_many({"_id": {"$in": ids}})


def test_rollup_is_idempotent(database):
    client, project_db = database
    # A rollup intentionally covers every device in the minute. Use a private
    # test database so live scenario traffic cannot change the expected count.
    test_name = project_db.name + "_rollup_test_" + uuid4().hex
    db = client[test_name]
    db.create_collection("events")
    db.create_collection("device_telemetry", timeseries={"timeField": "ts", "metaField": "deviceId", "granularity": "minutes"})
    bucket = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(minutes=2)
    ids = db.events.insert_many([{
        "ts": bucket + timedelta(seconds=i), "deviceId": "p5-rollup", "protocol": "ssh",
        "eventType": "login_failed" if i < 2 else "telemetry", "srcIp": "192.0.2.8",
        "geo": {"type": "Point", "coordinates": [77.59, 12.97]},
        "payload": {"user": "x", "attempts": 1} if i < 2 else {"bytesOut": 30, "bytesIn": 1},
        "prevHash": "0" * 64, "hash": f"{i:064x}",
    } for i in range(3)]).inserted_ids
    try:
        assert rollup_minute(db, bucket) == 1
        assert rollup_minute(db, bucket) == 0
        row = db.device_telemetry.find_one({"deviceId": "p5-rollup", "ts": bucket})
        assert (row["eventCount"], row["failedLogins"], row["bytesOut"]) == (3, 2, 30)
    finally:
        client.drop_database(test_name)
