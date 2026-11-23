"""Headless Phase 9 acceptance flow used by ``make demo``."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
BASE = os.getenv("DEMO_API_URL", f"http://localhost:{os.getenv('FRONTEND_PORT', '5173')}/api")


def check(condition: bool, label: str, detail: str = "") -> None:
    if not condition:
        raise AssertionError(f"{label}: {detail}")
    print(f"PASS {label}{': ' + detail if detail else ''}", flush=True)


def login(client: httpx.Client, username: str, password: str) -> dict:
    response = client.post("/auth/login", json={"username": username, "password": password})
    response.raise_for_status()
    return response.json()


def headers(session: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {session['access_token']}"}


def launch(client: httpx.Client, auth: dict[str, str], name: str, seed: int) -> dict:
    response = client.post("/scenarios/launch", headers=auth, json={"name": name, "seed": seed})
    response.raise_for_status()
    job_id = response.json()["id"]
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        jobs = client.get("/scenarios", headers=auth).json()
        job = next(item for item in jobs if item["id"] == job_id)
        if job["status"] == "completed":
            return job
        if job["status"] == "failed":
            raise AssertionError(f"scenario {name} failed: {job.get('error')}")
        time.sleep(0.1)
    raise AssertionError(f"scenario {name} timed out")


def wait_for_rule(client: httpx.Client, auth: dict[str, str], rule_id: str, timeout: float = 3) -> tuple[dict, float]:
    started = time.perf_counter()
    while time.perf_counter() - started < timeout:
        items = client.get("/alerts", headers=auth, params={"pageSize": 500}).json()["items"]
        match = next((item for item in items if item["ruleId"] == rule_id), None)
        if match:
            return match, time.perf_counter() - started
        time.sleep(0.05)
    raise AssertionError(f"no {rule_id} alert within {timeout}s")


def main() -> int:
    suffix = uuid4().hex[:8]
    with httpx.Client(base_url=BASE, timeout=30) as client:
        admin = login(client, os.getenv("APP_ADMIN_USERNAME", "admin"), os.environ["APP_ADMIN_PASSWORD"])
        analyst = login(client, os.getenv("APP_ANALYST_USERNAME", "analyst"), os.environ["APP_ANALYST_PASSWORD"])
        ah, nh = headers(admin), headers(analyst)

        mirai = launch(client, ah, "mirai_bruteforce", int(time.time()) % 100000)
        _, latency = wait_for_rule(client, ah, "R-BRUTE-01")
        check(latency <= 1.0, "1 Mirai alert in about one second", f"observed {latency:.3f}s; {len(mirai['insertedEventIds'])} events")

        lateral = launch(client, ah, "lateral_movement", int(time.time()) % 100000 + 1)
        incident = client.get(f"/incidents/{lateral['incidentId']}", headers=ah).json()
        hops = [item["hop"] for item in incident["chain"]]
        check(len(hops) >= 2 and hops == sorted(hops), "2 ordered lateral incident", f"incident={lateral['incidentId']} hops={hops}")

        rule_id = f"R-LIVE-{suffix}"
        rule = {"ruleId": rule_id, "name": "Phase 9 live rule", "stage": "credential-access", "severity": 9,
                "type": "windowed", "window": {"seconds": 300},
                "pipeline": [{"$match": {"srcIp": "{{srcIp}}", "eventType": "login_failed"}}, {"$limit": 1}],
                "active": True, "trigger": {"eventType": "login_failed"}, "cooldownSeconds": 1}
        created = client.post("/rules", headers=ah, json=rule)
        check(created.status_code == 201, "3 live rule created", rule_id)
        time.sleep(0.25)
        launch(client, ah, "mirai_bruteforce", int(time.time()) % 100000 + 2)
        _, live_latency = wait_for_rule(client, ah, rule_id)
        check(live_latency <= 1.0, "3 live rule fired without restart", f"observed {live_latency:.3f}s")

        risks = client.get("/risk", headers=ah).json()
        near = client.get("/devices/near", headers=ah, params={"lng": 77.59, "lat": 12.97, "radius": 50000}).json()
        compromised = {item["deviceId"] for item in risks if item.get("deviceId") and item.get("score", 0) > 0}
        nearby = {item["deviceId"] for item in near}
        check(bool(compromised & nearby), "4 risk map and radius", f"{len(compromised)} risky; {len(compromised & nearby)} nearby")

        tamper = client.post("/integrity/tamper-demo", headers=ah)
        tamper.raise_for_status()
        integrity = client.post("/integrity/check", headers=ah, json={"deviceId": None}).json()
        demo_devices = set(tamper.json()["devices"].values())
        demo_breaks = [item for item in integrity["breaks"] if item["deviceId"] in demo_devices]
        reasons = {item["reason"] for item in demo_breaks}
        check(reasons == {"modified", "missing", "reordered"}, "5 integrity pinpoints all tampering", str(sorted(reasons)))

        for stage in ("$out", "$function"):
            forbidden = {**rule, "ruleId": f"R-BAD-{stage[1:].upper()}-{suffix}", "pipeline": [{stage: "events"}]}
            response = client.post("/rules", headers=ah, json=forbidden)
            check(response.status_code == 422, f"6 forbidden {stage} rejected")

        denied = client.post("/rules", headers=nh, json={**rule, "ruleId": f"R-DENIED-{suffix}"})
        check(denied.status_code == 403, "7 analyst admin action denied")

        triaged = client.patch(f"/incidents/{lateral['incidentId']}/status", headers=ah, json={"status": "triaged"})
        closed = client.patch(f"/incidents/{lateral['incidentId']}/status", headers=ah, json={"status": "closed"})
        history = closed.json()["statusHistory"] if closed.status_code == 200 else []
        check(triaged.status_code == 200 and closed.status_code == 200 and [x["status"] for x in history][-3:] == ["open", "triaged", "closed"], "8 incident lifecycle history")

        client.delete(f"/rules/{rule_id}", headers=ah)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"FAIL {exc}", file=sys.stderr, flush=True)
        raise
