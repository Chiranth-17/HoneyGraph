"""Phase 1 integration tests for validation, idempotency, and RBAC."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus

import pytest
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import OperationFailure, WriteError

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
DB_NAME = os.getenv("MONGO_DATABASE", "honeygraph")


def _client(username: str, password: str) -> MongoClient[dict[str, Any]]:
    port = os.getenv("MONGO1_PORT", "27017")
    uri = (
        f"mongodb://{quote_plus(username)}:{quote_plus(password)}@localhost:{port}/{DB_NAME}"
        f"?authSource={DB_NAME}&replicaSet=rs0&directConnection=true"
    )
    return MongoClient(uri, serverSelectionTimeoutMS=5_000)


@pytest.fixture(scope="session")
def root_client() -> MongoClient[dict[str, Any]]:
    client = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=5_000)
    client.admin.command("ping")
    yield client
    client.close()


def event(protocol: str, payload: dict[str, Any]) -> dict[str, Any]:
    suffix = uuid.uuid4().hex
    return {
        "ts": datetime.now(timezone.utc),
        "deviceId": f"device-{suffix}",
        "protocol": protocol,
        "eventType": "integration_test",
        "srcIp": "198.51.100.20",
        "geo": {"type": "Point", "coordinates": [77.5946, 12.9716]},
        "payload": payload,
        "prevHash": "0" * 64,
        "hash": suffix.ljust(64, "0"),
    }


@pytest.mark.parametrize(
    ("protocol", "payload"),
    [
        ("ssh", {"user": "root", "attempts": 2}),
        ("telnet", {"user": "admin", "attempts": 1}),
        ("mqtt", {"topic": "sensors/temp", "clientId": "sensor-1", "action": "publish"}),
        ("http", {"method": "POST", "path": "/login", "username": "operator", "status": 401}),
        ("coap", {"uri": "/temperature", "code": "2.05"}),
    ],
)
def test_valid_event_for_each_protocol(root_client: MongoClient[dict[str, Any]], protocol: str, payload: dict[str, Any]) -> None:
    result = root_client[DB_NAME].events.insert_one(event(protocol, payload))
    assert result.acknowledged


@pytest.mark.parametrize(
    "mutation",
    [
        lambda doc: doc.update(protocol="ftp"),
        lambda doc: doc.update(payload={"unexpected": True}),
        lambda doc: doc.pop("deviceId"),
    ],
    ids=["wrong-enum", "wrong-payload-shape", "missing-required-field"],
)
def test_invalid_events_are_rejected(root_client: MongoClient[dict[str, Any]], mutation: Any) -> None:
    doc = event("ssh", {"user": "root", "attempts": 1})
    mutation(doc)
    with pytest.raises(WriteError) as error:
        root_client[DB_NAME].events.insert_one(doc)
    assert error.value.code == 121


def test_initializer_is_idempotent() -> None:
    command = [sys.executable, str(ROOT / "mongo" / "init_db.py")]
    first = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    assert first.returncode == 0, first.stderr
    assert second.returncode == 0, second.stderr


def _assert_denied(operation: Any) -> None:
    with pytest.raises(OperationFailure) as error:
        operation()
    assert error.value.code == 13


def test_ingest_service_permissions(root_client: MongoClient[dict[str, Any]]) -> None:
    with _client("ingest_svc", os.environ["MONGO_INGEST_PASSWORD"]) as client:
        db = client[DB_NAME]
        inserted = db.events.insert_one(event("ssh", {"user": "svc", "attempts": 0}))
        assert db.events.find_one({"_id": inserted.inserted_id}) is not None
        _assert_denied(lambda: db.alerts.insert_one({"probe": True}))


def test_detector_service_permissions(root_client: MongoClient[dict[str, Any]]) -> None:
    marker = uuid.uuid4().hex
    alert = {
        "ts": datetime.now(timezone.utc), "ruleId": "test", "deviceId": "device-test",
        "actor": marker, "targetIp": "203.0.113.5", "stage": "initial-access", "severity": 5,
        "eventIds": [ObjectId()], "eventInsertedAt": datetime.now(timezone.utc),
        "alertCreatedAt": datetime.now(timezone.utc),
    }
    with _client("detect_svc", os.environ["MONGO_DETECTOR_PASSWORD"]) as client:
        db = client[DB_NAME]
        assert db.events.find_one({}) is not None
        assert db.alerts.insert_one(alert).acknowledged
        assert db.incidents.insert_one({"marker": marker, "status": "open"}).acknowledged
        assert db.risk_scores.insert_one({"marker": marker, "score": 1}).acknowledged
        assert db.system_state.insert_one({"marker": marker}).acknowledged
        _assert_denied(lambda: db.events.insert_one(event("ssh", {"user": "x", "attempts": 1})))
        _assert_denied(lambda: db.rules.update_one({}, {"$set": {"active": False}}))


def test_analyst_permissions(root_client: MongoClient[dict[str, Any]]) -> None:
    with _client("analyst", os.environ["MONGO_ANALYST_PASSWORD"]) as client:
        db = client[DB_NAME]
        for name in ("devices", "events", "device_telemetry", "rules", "alerts", "incidents", "risk_scores", "users", "system_state", "ground_truth"):
            list(db[name].find({}).limit(1))
        _assert_denied(lambda: db.incidents.insert_one({"status": "open"}))


def test_rule_admin_permissions(root_client: MongoClient[dict[str, Any]]) -> None:
    rule_id = f"rule-{uuid.uuid4().hex}"
    rule = {"ruleId": rule_id, "name": "test", "stage": "discovery", "severity": 2,
            "type": "event", "window": {"seconds": 60}, "pipeline": [{"$match": {}}], "active": True}
    with _client("rule_admin", os.environ["MONGO_RULE_ADMIN_PASSWORD"]) as client:
        db = client[DB_NAME]
        assert db.rules.insert_one(rule).acknowledged
        assert db.rules.update_one({"ruleId": rule_id}, {"$set": {"active": False}}).modified_count == 1
        assert db.rules.delete_one({"ruleId": rule_id}).deleted_count == 1
        _assert_denied(lambda: db.events.find_one({}))


def test_tamper_demo_permissions(root_client: MongoClient[dict[str, Any]]) -> None:
    first_id = root_client[DB_NAME].events.insert_one(event("telnet", {"user": "x", "attempts": 1})).inserted_id
    second_id = root_client[DB_NAME].events.insert_one(event("telnet", {"user": "y", "attempts": 1})).inserted_id
    with _client("tamper_demo", os.environ["MONGO_TAMPER_PASSWORD"]) as client:
        db = client[DB_NAME]
        assert db.events.update_one({"_id": first_id}, {"$set": {"eventType": "tampered"}}).modified_count == 1
        assert db.events.delete_one({"_id": second_id}).deleted_count == 1
        _assert_denied(lambda: db.events.insert_one(event("ssh", {"user": "x", "attempts": 1})))


def test_api_service_permissions(root_client: MongoClient[dict[str, Any]]) -> None:
    marker = uuid.uuid4().hex
    incident_id = root_client[DB_NAME].incidents.insert_one({"marker": marker, "status": "open"}).inserted_id
    with _client("api_svc", os.environ["MONGO_API_PASSWORD"]) as client:
        db = client[DB_NAME]
        list(db.events.find({}).limit(1))
        list(db.rules.find({}).limit(1))
        assert db.users.insert_one({"username": f"test-{marker}"}).acknowledged
        assert db.incidents.update_one({"_id": incident_id}, {"$set": {"status": "closed"}}).modified_count == 1
        _assert_denied(lambda: db.rules.update_one({}, {"$set": {"active": False}}))
        _assert_denied(lambda: db.alerts.insert_one({"probe": True}))

