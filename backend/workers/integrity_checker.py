"""Per-device hash-chain verification and externally anchored checkpoints."""

from __future__ import annotations

import argparse
import json
import os
import signal
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

from app.hashchain import GENESIS_HASH, compute_hash

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
CHECKPOINT_STATE_ID = "integrity.checkpoint.latest"


@dataclass(frozen=True)
class IntegrityBreak:
    deviceId: str
    position: int
    expectedHash: str
    storedHash: str
    reason: str


def _ordered_events(db: Database[Any], device_id: str) -> Iterable[dict[str, Any]]:
    return db.events.find({"deviceId": device_id}).sort([("ts", 1), ("_id", 1)])


def check_device(db: Database[Any], device_id: str) -> IntegrityBreak | None:
    """Return only the first broken link for one device."""
    previous = GENESIS_HASH
    expected_sequence = 1
    events = list(_ordered_events(db, device_id))
    for position, event in enumerate(events, start=1):
        sequence = event.get("chainSeq")
        if sequence is not None and sequence != expected_sequence:
            remaining_sequences = {item.get("chainSeq") for item in events[position:]}
            reason = "reordered" if expected_sequence in remaining_sequences else "missing"
            return IntegrityBreak(device_id, expected_sequence if reason == "missing" else position, previous, event.get("prevHash", ""), reason)
        if event.get("prevHash") != previous:
            return IntegrityBreak(device_id, position, previous, event.get("prevHash", ""), "missing")
        calculated = compute_hash(previous, event)
        if event.get("hash") != calculated:
            return IntegrityBreak(device_id, position, calculated, event.get("hash", ""), "modified")
        previous = event["hash"]
        expected_sequence += 1
    return None


def check_all(
    db: Database[Any], device_id: str | None = None, *, progress_every: int = 50,
    reporter: Callable[[str], None] | None = print,
) -> tuple[list[IntegrityBreak], int, float]:
    """Check one/all devices with bounded progress messages."""
    started = time.perf_counter()
    devices = [device_id] if device_id else db.events.distinct("deviceId")
    breaks: list[IntegrityBreak] = []
    checked_events = 0
    for index, current in enumerate(sorted(devices), start=1):
        checked_events += db.events.count_documents({"deviceId": current})
        broken = check_device(db, current)
        if broken:
            breaks.append(broken)
        if reporter and (index % progress_every == 0 or index == len(devices)):
            reporter(f"progress devices={index}/{len(devices)} events={checked_events} breaks={len(breaks)}")
    return breaks, checked_events, time.perf_counter() - started


def _json_value(value: Any) -> Any:
    if isinstance(value, (datetime, ObjectId)):
        return value.isoformat() if isinstance(value, datetime) else str(value)
    raise TypeError(f"cannot serialize {type(value).__name__}")


def export_checkpoint(
    db: Database[Any], directory: Path, *, device_ids: Iterable[str] | None = None,
    created_at: datetime | None = None,
) -> Path:
    """Persist operational state in MongoDB and the same anchor outside MongoDB."""
    moment = (created_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    ids = sorted(set(device_ids or db.events.distinct("deviceId")))
    anchors: dict[str, dict[str, Any]] = {}
    for device_id in ids:
        tail = db.events.find_one({"deviceId": device_id}, sort=[("ts", -1), ("_id", -1)])
        if tail:
            anchors[device_id] = {
                "hash": tail["hash"], "eventId": tail["_id"], "ts": tail["ts"],
                "chainSeq": tail.get("chainSeq"), "eventCount": db.events.count_documents({"deviceId": device_id}),
            }
    document = {"createdAt": moment, "devices": anchors}
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{moment:%Y%m%d%H%M}.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(document, default=_json_value, sort_keys=True, indent=2), encoding="utf-8")
    temporary.replace(path)
    db.system_state.replace_one(
        {"_id": CHECKPOINT_STATE_ID}, {"_id": CHECKPOINT_STATE_ID, **document, "externalPath": str(path.resolve())}, upsert=True
    )
    return path


def compare_checkpoint(db: Database[Any], path: Path) -> list[IntegrityBreak]:
    """Compare live tails to a trusted external anchor and report truncation."""
    checkpoint = json.loads(path.read_text(encoding="utf-8"))
    breaks: list[IntegrityBreak] = []
    for device_id, anchor in sorted(checkpoint["devices"].items()):
        anchored = db.events.find_one({"_id": ObjectId(anchor["eventId"]), "deviceId": device_id})
        live_count = db.events.count_documents({"deviceId": device_id})
        if anchored is None or live_count < anchor["eventCount"]:
            tail = db.events.find_one({"deviceId": device_id}, sort=[("ts", -1), ("_id", -1)])
            breaks.append(IntegrityBreak(
                device_id, int(anchor.get("chainSeq") or anchor["eventCount"]), anchor["hash"],
                tail["hash"] if tail else GENESIS_HASH, "truncated",
            ))
    return breaks


def latest_checkpoint(directory: Path) -> Path:
    candidates = sorted(directory.glob("????????????.json"))
    if not candidates:
        raise FileNotFoundError(f"no checkpoints in {directory}")
    return candidates[-1]


def checkpoint_forever(db: Database[Any], directory: Path, interval_minutes: float, stopped: threading.Event) -> None:
    """Periodically refresh external and database anchors until signaled."""
    if interval_minutes <= 0:
        raise ValueError("checkpoint interval must be positive")
    while not stopped.is_set():
        print(f"checkpoint={export_checkpoint(db, directory)}", flush=True)
        stopped.wait(interval_minutes * 60)


def tamper_uri() -> str:
    database = os.getenv("MONGO_DATABASE", "honeygraph")
    port = os.getenv("MONGO1_PORT", "27017")
    return (
        f"mongodb://tamper_demo:{os.environ['MONGO_TAMPER_PASSWORD']}@localhost:{port}/{database}"
        f"?authSource={database}&replicaSet=rs0&directConnection=true"
    )


class TamperDemo:
    """Trusted admin helper that mutates only explicitly selected event IDs."""

    def __init__(self, db: Database[Any]) -> None:
        self.events = db.events

    def edit(self, event_id: ObjectId) -> int:
        return self.events.update_one({"_id": event_id}, {"$set": {"eventType": "tampered_demo"}}).modified_count

    def delete(self, event_id: ObjectId) -> int:
        return self.events.delete_one({"_id": event_id}).deleted_count

    def swap(self, first_id: ObjectId, first_ts: datetime, second_id: ObjectId, second_ts: datetime) -> int:
        first = self.events.update_one({"_id": first_id}, {"$set": {"ts": second_ts}}).modified_count
        second = self.events.update_one({"_id": second_id}, {"$set": {"ts": first_ts}}).modified_count
        return first + second


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify HoneyGraph per-device hash chains")
    parser.add_argument("--device")
    parser.add_argument("--checkpoint", action="store_true")
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--compare-latest", action="store_true")
    parser.add_argument("--checkpoint-interval-minutes", type=float)
    parser.add_argument("--checkpoint-dir", type=Path, default=ROOT / "checkpoints")
    args = parser.parse_args()
    with MongoClient(os.environ["MONGODB_URI"]) as client:
        db = client[os.getenv("MONGO_DATABASE", "honeygraph")]
        breaks, events, elapsed = check_all(db, args.device)
        for broken in breaks:
            print(json.dumps(asdict(broken), sort_keys=True))
        if args.checkpoint:
            print(f"checkpoint={export_checkpoint(db, args.checkpoint_dir)}")
        if args.compare:
            for broken in compare_checkpoint(db, args.compare):
                print(json.dumps(asdict(broken), sort_keys=True))
        if args.compare_latest:
            for broken in compare_checkpoint(db, latest_checkpoint(args.checkpoint_dir)):
                print(json.dumps(asdict(broken), sort_keys=True))
        rate = events / elapsed if elapsed else 0
        print(f"checked_events={events} breaks={len(breaks)} seconds={elapsed:.3f} events_per_second={rate:.1f}")
        if args.checkpoint_interval_minutes:
            stopped = threading.Event()
            signal.signal(signal.SIGTERM, lambda *_: stopped.set())
            signal.signal(signal.SIGINT, lambda *_: stopped.set())
            checkpoint_forever(db, args.checkpoint_dir, args.checkpoint_interval_minutes, stopped)


if __name__ == "__main__":
    main()
