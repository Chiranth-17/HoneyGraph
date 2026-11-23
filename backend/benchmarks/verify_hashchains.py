"""Quick end-to-end verifier for API-ingested per-device event chains."""

from __future__ import annotations

import argparse
import os
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pymongo import MongoClient

from app.hashchain import GENESIS_HASH, verify_link

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def verify(match: dict[str, Any] | None = None) -> tuple[int, int, float]:
    started = time.perf_counter()
    with MongoClient(os.environ["MONGODB_URI"]) as client:
        events = client[os.getenv("MONGO_DATABASE", "honeygraph")].events
        cursor = events.find(match or {"chainSeq": {"$exists": True}}).sort([("deviceId", 1), ("chainSeq", 1)])
        previous: dict[str, str] = defaultdict(lambda: GENESIS_HASH)
        sequences: dict[str, int] = defaultdict(int)
        count = 0
        for event in cursor:
            device_id = event["deviceId"]
            sequences[device_id] += 1
            if event["chainSeq"] != sequences[device_id]:
                raise AssertionError(f"sequence gap for {device_id}: expected {sequences[device_id]}, got {event['chainSeq']}")
            if not verify_link(event, previous[device_id]):
                raise AssertionError(f"hash-chain failure for {device_id} at sequence {event['chainSeq']}")
            previous[device_id] = event["hash"]
            count += 1
    return count, len(previous), time.perf_counter() - started


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-id", help="optional ingest batch ID filter")
    args = parser.parse_args()
    match = {"ingestBatchId": args.batch_id} if args.batch_id else None
    events, devices, elapsed = verify(match)
    print(f"verified_events={events} devices={devices} seconds={elapsed:.3f}")


if __name__ == "__main__":
    main()
