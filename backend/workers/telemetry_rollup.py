"""Idempotent per-minute event rollups into the time-series collection."""

from __future__ import annotations

import hashlib
import os
import signal
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from pymongo.database import Database
from pymongo.errors import BulkWriteError


def minute_bucket(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc).replace(second=0, microsecond=0)


def rollup_minute(db: Database[Any], bucket: datetime) -> int:
    """Aggregate in MongoDB and retry safely using deterministic BSON identifiers."""
    start = minute_bucket(bucket)
    end = start + timedelta(minutes=1)
    rows = list(db.events.aggregate([
        {"$match": {"ts": {"$gte": start, "$lt": end}}},
        {"$group": {
            "_id": "$deviceId", "eventCount": {"$sum": 1},
            "failedLogins": {"$sum": {"$cond": [{"$eq": ["$eventType", "login_failed"]}, 1, 0]}},
            "bytesOut": {"$sum": {"$ifNull": ["$payload.bytesOut", 0]}},
        }},
        {"$project": {"_id": 0, "deviceId": "$_id", "ts": {"$literal": start}, "eventCount": 1, "failedLogins": 1, "bytesOut": 1}},
    ]))
    for row in rows:
        row["_id"] = ObjectId(hashlib.sha256(f"{row['deviceId']}|{start.isoformat()}".encode()).digest()[:12])
    existing = {
        item["deviceId"]
        for item in db.device_telemetry.find(
            {"ts": start, "deviceId": {"$in": [row["deviceId"] for row in rows]}}, {"deviceId": 1}
        )
    }
    rows = [row for row in rows if row["deviceId"] not in existing]
    if not rows:
        return 0
    try:
        return len(db.device_telemetry.insert_many(rows, ordered=False).inserted_ids)
    except BulkWriteError as exc:
        errors = exc.details.get("writeErrors", [])
        if any(error.get("code") != 11000 for error in errors):
            raise
        return exc.details.get("nInserted", 0)


def main() -> None:
    from pymongo import MongoClient
    from workers.detector import detector_uri
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    with MongoClient(detector_uri()) as client:
        db = client[os.getenv("MONGO_DATABASE", "honeygraph")]
        while not stopped.is_set():
            count = rollup_minute(db, datetime.now(timezone.utc) - timedelta(minutes=1))
            print(f"telemetry_rollups_inserted={count}", flush=True)
            seconds = 60 - time.time() % 60
            stopped.wait(seconds)


if __name__ == "__main__":
    main()
