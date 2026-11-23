"""Phase 7 REST, RBAC, OpenAPI, and WebSocket integration gates."""

from __future__ import annotations

import os
import threading
import time
from datetime import datetime, timezone

import pytest
from bson import ObjectId
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from pymongo import MongoClient

from app.hashchain import GENESIS_HASH, compute_hash
from app.main import app

load_dotenv()
DB_NAME = os.getenv("MONGO_DATABASE", "honeygraph")


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as instance:
        yield instance


@pytest.fixture(scope="module")
def root():
    with MongoClient(os.environ["MONGODB_URI"]) as connection:
        yield connection[DB_NAME]


@pytest.fixture(scope="module")
def tokens(client):
    analyst = client.post("/api/auth/login", json={"username": os.getenv("APP_ANALYST_USERNAME", "analyst"), "password": os.environ["APP_ANALYST_PASSWORD"]})
    admin = client.post("/api/auth/login", json={"username": os.getenv("APP_ADMIN_USERNAME", "admin"), "password": os.environ["APP_ADMIN_PASSWORD"]})
    assert analyst.status_code == admin.status_code == 200
    return analyst.json()["access_token"], admin.json()["access_token"]


def headers(token): return {"Authorization": f"Bearer {token}"}


def test_auth_openapi_and_role_boundaries(client, tokens):
    analyst, admin = tokens
    assert client.get("/api/alerts").status_code == 401
    assert client.get("/api/users", headers=headers(analyst)).status_code == 403
    assert client.get("/api/users", headers=headers(admin)).status_code == 200
    schema = client.get("/openapi.json").json()
    assert "/api/alerts" in schema["paths"] and "/api/rules" in schema["paths"]


def test_alerts_filters_and_pagination(client, root, tokens):
    alert = {"ts": datetime.now(timezone.utc), "ruleId": "API-ALERT", "deviceId": "api-device", "actor": "192.0.2.1", "targetIp": "10.0.0.1", "stage": "test-stage", "severity": 4, "eventIds": [ObjectId()], "eventInsertedAt": datetime.now(timezone.utc), "alertCreatedAt": datetime.now(timezone.utc), "dedupeKey": str(ObjectId())}
    identifier = root.alerts.insert_one(alert).inserted_id
    try:
        response = client.get("/api/alerts?device=api-device&stage=test-stage&pageSize=1", headers=headers(tokens[0]))
        assert response.status_code == 200 and response.json()["total"] == 1
    finally: root.alerts.delete_one({"_id": identifier})


def test_incident_detail_and_strict_transitions(client, root, tokens):
    identifier = root.incidents.insert_one({"status": "open", "createdAt": datetime.now(timezone.utc), "updatedAt": datetime.now(timezone.utc), "statusHistory": []}).inserted_id
    try:
        assert client.get(f"/api/incidents/{identifier}", headers=headers(tokens[0])).status_code == 200
        assert client.patch(f"/api/incidents/{identifier}/status", json={"status": "closed"}, headers=headers(tokens[0])).status_code == 409
        assert client.patch(f"/api/incidents/{identifier}/status", json={"status": "triaged"}, headers=headers(tokens[0])).status_code == 200
        closed = client.patch(f"/api/incidents/{identifier}/status", json={"status": "closed"}, headers=headers(tokens[0]))
        assert closed.status_code == 200 and len(closed.json()["statusHistory"]) == 2
    finally: root.incidents.delete_one({"_id": identifier})


def test_devices_near_and_timeline(client, tokens):
    listed = client.get("/api/devices?pageSize=2", headers=headers(tokens[0]))
    assert listed.status_code == 200 and listed.json()["items"]
    device = listed.json()["items"][0]
    near = client.get("/api/devices/near?lng=77.5946&lat=12.9716&radius=100000", headers=headers(tokens[0]))
    timeline = client.get(f"/api/devices/{device['deviceId']}/timeline?pageSize=2", headers=headers(tokens[0]))
    assert near.status_code == timeline.status_code == 200


def test_risk_routes(client, root, tokens):
    root.risk_scores.replace_one({"deviceId": "api-risk"}, {"deviceId": "api-risk", "score": 42.0, "factors": []}, upsert=True)
    try:
        assert client.get("/api/risk", headers=headers(tokens[0])).status_code == 200
        assert client.get("/api/risk/api-risk", headers=headers(tokens[0])).json()["score"] == 42.0
    finally: root.risk_scores.delete_one({"deviceId": "api-risk"})


def test_rules_crud_validation_enable_and_hits(client, tokens):
    analyst, admin = tokens
    rule = {"ruleId": "API-RULE", "name": "API test", "stage": "test", "severity": 4, "type": "windowed", "window": {"seconds": 60}, "pipeline": [{"$match": {"deviceId": "{{deviceId}}"}}], "active": True}
    assert client.post("/api/rules", json=rule, headers=headers(analyst)).status_code == 403
    assert client.post("/api/rules", json={**rule, "pipeline": [{"$out": "events"}]}, headers=headers(admin)).status_code == 422
    try:
        assert client.post("/api/rules", json=rule, headers=headers(admin)).status_code == 201
        assert client.patch("/api/rules/API-RULE/enabled", json={"active": False}, headers=headers(admin)).json()["active"] is False
        assert "hitCount" in next(item for item in client.get("/api/rules", headers=headers(analyst)).json() if item["ruleId"] == "API-RULE")
    finally: client.delete("/api/rules/API-RULE", headers=headers(admin))


def test_integrity_results_and_admin_tamper(client, root, tokens):
    device = "api-integrity"
    ts = datetime.now(timezone.utc).replace(microsecond=0)
    event = {"ts": ts, "deviceId": device, "protocol": "ssh", "eventType": "login_failed", "srcIp": "192.0.2.4", "geo": {"type": "Point", "coordinates": [77.59, 12.97]}, "payload": {"user": "x", "attempts": 1}, "prevHash": GENESIS_HASH, "chainSeq": 1}
    event["hash"] = compute_hash(GENESIS_HASH, event)
    identifier = root.events.insert_one(event).inserted_id
    try:
        checked = client.post("/api/integrity/check", json={"deviceId": device}, headers=headers(tokens[0]))
        assert checked.status_code == 200 and checked.json()["breaks"] == []
        assert client.get("/api/integrity/results", headers=headers(tokens[0])).status_code == 200
        assert client.post("/api/integrity/tamper", json={"action": "edit", "eventIds": [str(identifier)]}, headers=headers(tokens[0])).status_code == 403
        assert client.post("/api/integrity/tamper", json={"action": "edit", "eventIds": [str(identifier)]}, headers=headers(tokens[1])).status_code == 200
    finally: root.events.delete_many({"deviceId": device})


def test_user_management(client, root, tokens):
    username = "api-test-user"
    root.users.delete_one({"username": username})
    try:
        created = client.post("/api/users", json={"username": username, "password": "password123", "role": "analyst"}, headers=headers(tokens[1]))
        assert created.status_code == 201
        assert client.patch(f"/api/users/{username}", json={"active": False}, headers=headers(tokens[1])).status_code == 200
    finally: root.users.delete_one({"username": username})


def test_scenario_launch_list_and_stop(client, tokens):
    response = client.post("/api/scenarios/launch", json={"name": "mqtt_abuse", "seed": 707}, headers=headers(tokens[1]))
    assert response.status_code == 202
    job_id = response.json()["id"]
    assert client.get("/api/scenarios", headers=headers(tokens[1])).status_code == 200
    assert client.post(f"/api/scenarios/{job_id}/stop", headers=headers(tokens[1])).status_code == 200


def test_stats_dashboard(client, tokens):
    response = client.get("/api/stats/dashboard", headers=headers(tokens[0]))
    assert response.status_code == 200
    assert {"alertsByStage", "severityOverTime", "topRiskyDevices"} == set(response.json())


def test_websocket_receives_alert_within_one_second(client, root, tokens):
    alert = {"ts": datetime.now(timezone.utc), "ruleId": "API-WS", "deviceId": "api-ws", "actor": "192.0.2.9", "targetIp": "10.0.0.9", "stage": "test", "severity": 3, "eventIds": [ObjectId()], "eventInsertedAt": datetime.now(timezone.utc), "alertCreatedAt": datetime.now(timezone.utc), "dedupeKey": str(ObjectId())}
    with client.websocket_connect(f"/ws/alerts?token={tokens[0]}") as socket:
        timer = threading.Timer(0.1, lambda: root.alerts.insert_one(alert))
        started = time.perf_counter(); timer.start()
        received = socket.receive_json(); elapsed = time.perf_counter() - started
        timer.join()
    root.alerts.delete_one({"dedupeKey": alert["dedupeKey"]})
    print(f"websocket_delivery_seconds={elapsed:.3f}")
    assert received["ruleId"] == "API-WS" and elapsed < 1.0
