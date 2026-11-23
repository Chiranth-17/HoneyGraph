"""Presentation flow must expose real evidence before explicit correlation."""
import asyncio
import os
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from bson import ObjectId
from dotenv import load_dotenv
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pymongo import MongoClient

from app.api_models import ScenarioRequest
from app.hashchain import GENESIS_HASH, compute_hash
from app.main import app
from app.routers import scenarios

load_dotenv()


def test_guided_run_stops_after_detection_without_building_incidents(monkeypatch):
    called = []
    detected = [{"_id": ObjectId()}]

    async def ingest(events):
        return [{"id": str(ObjectId())} for _ in events]

    monkeypatch.setattr(scenarios, "_wait_for_scenario_alerts", lambda *args: detected, raising=False)
    monkeypatch.setattr(scenarios, "_build_scenario_incidents", lambda *args: called.append(args))
    instance = SimpleNamespace(state=SimpleNamespace(
        scenario_jobs={"guided": {}},
        db=SimpleNamespace(devices=SimpleNamespace(find=lambda *args: [])),
        ingestion=SimpleNamespace(ingest=ingest),
    ))
    body = ScenarioRequest(name="mirai_bruteforce", seed=917, deferCorrelation=True)
    asyncio.run(scenarios.execute(instance, "guided", body))
    job = instance.state.scenario_jobs["guided"]
    assert not called
    assert job["status"] == "awaiting_correlation"
    assert len(job["insertedEventIds"]) == 18
    assert job["alertCount"] == 1
    assert job["incidentIds"] == []


def test_explicit_correlation_is_idempotent(monkeypatch):
    calls = []
    incident_id = str(ObjectId())
    job = {"name": "lateral_movement", "deferCorrelation": True,
           "status": "awaiting_correlation", "insertedEventIds": [str(ObjectId())]}
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(scenario_jobs={"guided": job})))

    def build(*args):
        calls.append(args)
        return [incident_id]

    monkeypatch.setattr(scenarios, "_build_scenario_incidents", build)
    first = asyncio.run(scenarios.correlate("guided", request, {"username": "admin"}))
    second = asyncio.run(scenarios.correlate("guided", request, {"username": "admin"}))
    assert first["incidentIds"] == second["incidentIds"] == [incident_id]
    assert len(calls) == 1


def test_correlation_refuses_a_run_still_detecting():
    job = {"name": "mirai_bruteforce", "deferCorrelation": True, "status": "detecting"}
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(scenario_jobs={"guided": job})))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(scenarios.correlate("guided", request, {}))
    assert exc.value.status_code == 409


def test_concurrent_correlation_is_rejected_while_builder_is_running(monkeypatch):
    import threading

    started, release = threading.Event(), threading.Event()
    job = {"name": "lateral_movement", "deferCorrelation": True,
           "status": "awaiting_correlation", "insertedEventIds": [str(ObjectId())]}
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(scenario_jobs={"guided": job})))

    def build(*args):
        started.set()
        assert release.wait(5)
        return [str(ObjectId())]

    monkeypatch.setattr(scenarios, "_build_scenario_incidents", build)

    async def simultaneous():
        first = asyncio.create_task(scenarios.correlate("guided", request, {}))
        assert await asyncio.to_thread(started.wait, 5)
        try:
            with pytest.raises(HTTPException) as exc:
                await scenarios.correlate("guided", request, {})
            assert exc.value.status_code == 409
        finally:
            release.set()
        await first

    asyncio.run(simultaneous())


def test_failed_correlation_can_be_retried(monkeypatch):
    job = {"name": "mirai_bruteforce", "deferCorrelation": True,
           "status": "awaiting_correlation", "insertedEventIds": [str(ObjectId())]}
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(scenario_jobs={"guided": job})))

    def fail(*args):
        raise RuntimeError("transaction failed")

    monkeypatch.setattr(scenarios, "_build_scenario_incidents", fail)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(scenarios.correlate("guided", request, {}))
    assert exc.value.status_code == 503
    assert job["status"] == "awaiting_correlation"
    assert "transaction failed" in job["error"]


@pytest.fixture
def evidence_client():
    """Create only isolated test observations; remove only these fixture IDs."""
    marker = "guided-test-" + uuid4().hex
    now = datetime.now(timezone.utc)
    with MongoClient(os.environ["MONGODB_URI"]) as root, TestClient(app) as client:
        db = root[os.getenv("MONGO_DATABASE", "honeygraph")]
        events = []
        for suffix in ("selected", "other"):
            row = {"ts": now, "deviceId": marker + suffix, "protocol": "ssh",
                   "eventType": "guided_test", "srcIp": "192.0.2.219",
                   "geo": {"type": "Point", "coordinates": [77.59, 12.97]},
                   "payload": {"user": "fixture", "attempts": 1},
                   "prevHash": GENESIS_HASH, "chainSeq": 1, "eventInsertedAt": now,
                   "ingestBatchId": marker + suffix}
            row["hash"] = compute_hash(GENESIS_HASH, row)
            events.append(row)
        ids = db.events.insert_many(events).inserted_ids
        alert_ids = []
        for event_id in ids:
            alert_ids.append(db.alerts.insert_one({
                "ts": now, "ruleId": marker, "deviceId": marker,
                "actor": "192.0.2.219", "targetIp": "10.42.0.1", "stage": "fixture",
                "severity": 3, "eventIds": [event_id], "eventInsertedAt": now,
                "alertCreatedAt": now, "dedupeKey": uuid4().hex,
            }).inserted_id)
        incident_id = db.incidents.insert_one({"status": "open", "chain": [{"alertId": alert_ids[0]}]}).inserted_id
        app.state.scenario_jobs[marker] = {"id": marker, "insertedEventIds": [str(ids[0])]}
        sessions = {}
        for role in ("admin", "analyst"):
            result = client.post("/api/auth/login", json={
                "username": os.getenv(f"APP_{role.upper()}_USERNAME", role),
                "password": os.environ[f"APP_{role.upper()}_PASSWORD"],
            })
            sessions[role] = {"Authorization": "Bearer " + result.json()["access_token"]}
        try:
            yield client, marker, ids, alert_ids, incident_id, sessions
        finally:
            db.incidents.delete_one({"_id": incident_id})
            db.alerts.delete_many({"_id": {"$in": alert_ids}})
            db.events.delete_many({"_id": {"$in": ids}})


def test_evidence_is_scoped_to_the_selected_run(evidence_client):
    client, job_id, events, alerts, incident, sessions = evidence_client
    response = client.get(f"/api/scenarios/{job_id}/evidence", headers=sessions["admin"])
    assert response.status_code == 200
    data = response.json()
    assert data["counts"] == {"events": 1, "alerts": 1, "incidents": 1}
    assert [row["_id"] for row in data["events"]] == [str(events[0])]
    assert [row["_id"] for row in data["alerts"]] == [str(alerts[0])]
    assert [row["_id"] for row in data["incidents"]] == [str(incident)]
    assert str(events[1]) not in response.text


def test_guided_endpoints_require_admin(evidence_client):
    client, job_id, _, _, _, sessions = evidence_client
    for path, method in [(f"/api/scenarios/{job_id}/evidence", "get"),
                         (f"/api/scenarios/{job_id}/correlate", "post")]:
        assert getattr(client, method)(path).status_code == 401
        assert getattr(client, method)(path, headers=sessions["analyst"]).status_code == 403
