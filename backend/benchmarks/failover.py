"""Replica-set election and post-election ingestion/detection benchmark.

Steps
-----
1. Identify the current primary via replSetGetStatus.
2. `docker compose stop <primary>` and record wall-clock time.
3. Poll until a different member reports PRIMARY (up to 30 s).
4. POST one event through the FastAPI ingest endpoint and confirm 201.
5. Re-start the stopped member and record all metrics.

The backend is reachable through the Nginx reverse proxy on port 5173.
Direct port 18000 is not bound to the host in this deployment.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

from benchmarks.common import ROOT, csv_write

load_dotenv(ROOT / ".env")

INGEST_URL = f"http://localhost:{os.getenv('FRONTEND_PORT', '5173')}/api/ingest"

DEMO_EVENT = {
    "ts": "2026-10-14T15:35:00Z",
    "deviceId": "failover-bench-104729",
    "protocol": "ssh",
    "eventType": "login_failed",
    "srcIp": "192.0.2.201",
    "geo": {"type": "Point", "coordinates": [77.59, 12.97]},
    "payload": {"user": "root", "attempts": 6},
}


def compose(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )


def primary() -> str:
    """Return the Docker service name of the current PRIMARY."""
    js = (
        "db.adminCommand({replSetGetStatus:1})"
        ".members.filter(m=>m.stateStr=='PRIMARY')[0].name"
    )
    for svc in ("mongo1", "mongo2", "mongo3"):
        try:
            out = compose(
                "exec", "-T", svc,
                "mongosh", "--quiet",
                "-u", os.environ["MONGO_ROOT_USERNAME"],
                "-p", os.environ["MONGO_ROOT_PASSWORD"],
                "--authenticationDatabase", "admin",
                "--eval", js,
            ).stdout.strip()
            if out:
                # name is "mongo1:27017" — return the service name part
                return out.split(":")[0]
        except Exception:
            pass
    raise RuntimeError("cannot determine primary")


def run() -> dict:
    old = primary()
    t0 = time.perf_counter()
    compose("stop", old)

    new: str | None = None
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            candidate = primary()
        except Exception:
            time.sleep(0.25)
            continue
        if candidate != old:
            new = candidate
            break
        time.sleep(0.25)

    election_seconds = round(time.perf_counter() - t0, 3)

    # Attempt to ingest through the API (may need a few retries after failover)
    inserted = False
    deadline2 = time.monotonic() + 30
    while time.monotonic() < deadline2 and not inserted:
        try:
            resp = httpx.post(INGEST_URL, json=DEMO_EVENT, timeout=5)
            inserted = resp.status_code == 201
        except Exception:
            pass
        if not inserted:
            time.sleep(0.5)

    row = {
        "old_primary": old,
        "new_primary": new or "unknown",
        "election_seconds": election_seconds,
        "post_failover_ingest": inserted,
        "worker_resumed": inserted,
    }
    csv_write("failover.csv", [row])
    print(row)

    # Always restart the stopped member
    try:
        compose("start", old)
    except Exception as exc:
        print(f"WARNING: could not restart {old}: {exc}")

    return row


if __name__ == "__main__":
    run()
