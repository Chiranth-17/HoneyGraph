"""MongoDB change-stream detection-as-data worker."""

from __future__ import annotations

import hashlib
import logging
import os
import signal
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError, PyMongoError
from pymongo.write_concern import WriteConcern

from app.rule_validator import substitute_placeholders, validate_rule

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
LOGGER = logging.getLogger("honeygraph.detector")
RESUME_STATE_ID = "detector.events.resume"


def detector_uri() -> str:
    explicit = os.getenv("MONGO_DETECTOR_URI")
    if explicit:
        return explicit
    database = os.getenv("MONGO_DATABASE", "honeygraph")
    port = os.getenv("MONGO1_PORT", "27017")
    password = os.environ["MONGO_DETECTOR_PASSWORD"]
    return (
        f"mongodb://detect_svc:{password}@localhost:{port}/{database}"
        f"?authSource={database}&replicaSet=rs0&directConnection=true"
    )


class Detector:
    """Evaluate cached rule documents for each inserted event."""

    def __init__(self, client: MongoClient, database: str, max_time_ms: int = 2_000) -> None:
        self.client = client
        self.db = client[database]
        self.events = self.db.events
        self.rules = self.db.rules
        self.alerts: Collection = self.db.alerts.with_options(write_concern=WriteConcern("majority"))
        self.state = self.db.system_state
        self.max_time_ms = max_time_ms
        self._rules: list[dict[str, Any]] = []
        self._rules_lock = threading.RLock()
        self._stop = threading.Event()
        self._rule_thread: threading.Thread | None = None

    def reload_rules(self) -> None:
        loaded: list[dict[str, Any]] = []
        for rule in self.rules.find({"active": True}):
            try:
                loaded.append(validate_rule(rule))
            except ValueError as exc:
                LOGGER.error("Skipping invalid rule %s: %s", rule.get("ruleId"), exc)
        with self._rules_lock:
            self._rules = loaded
        LOGGER.info("Loaded %d active rules", len(loaded))

    def _watch_rules(self) -> None:
        while not self._stop.is_set():
            try:
                with self.rules.watch(max_await_time_ms=1_000) as stream:
                    while not self._stop.is_set():
                        if stream.try_next() is not None:
                            self.reload_rules()
            except PyMongoError:
                LOGGER.exception("Rule change stream failed; retrying")
                self._stop.wait(1)

    def start_rule_cache(self) -> None:
        self.reload_rules()
        self._rule_thread = threading.Thread(target=self._watch_rules, name="rule-cache", daemon=True)
        self._rule_thread.start()

    @staticmethod
    def _trigger_matches(rule: dict[str, Any], event: dict[str, Any]) -> bool:
        trigger = rule.get("trigger", {})
        return all(event.get(key) == value for key, value in trigger.items())

    def _baseline_matches(self, rule: dict[str, Any], event: dict[str, Any]) -> bool:
        if rule["type"] != "baseline":
            return True
        current = event.get("payload", {}).get("bytesOut")
        if current is None:
            return False
        result = list(
            self.db.device_telemetry.aggregate(
                [
                    {"$match": {"deviceId": event["deviceId"]}},
                    {"$group": {"_id": "$deviceId", "average": {"$avg": "$bytesOut"}}},
                    {"$limit": 1},
                ],
                maxTimeMS=self.max_time_ms,
            )
        )
        return bool(result and current >= result[0]["average"] * rule.get("baselineMultiplier", 5))

    def _evaluate(self, rule: dict[str, Any], event: dict[str, Any]) -> list[dict[str, Any]]:
        validate_rule(rule)  # Defense in depth immediately before execution.
        if not self._trigger_matches(rule, event) or not self._baseline_matches(rule, event):
            return []
        seconds = rule["window"]["seconds"]
        context = {"srcIp": event["srcIp"], "deviceId": event["deviceId"], "ts": event["ts"], "eventId": event["_id"]}
        time_match = {"$match": {"ts": {"$gte": event["ts"] - timedelta(seconds=seconds), "$lte": event["ts"]}}}
        pipeline = [time_match, *substitute_placeholders(rule["pipeline"], context)]
        return list(self.events.aggregate(pipeline, maxTimeMS=self.max_time_ms))

    @staticmethod
    def _event_ids(results: list[dict[str, Any]], current_id: Any) -> list[Any]:
        identifiers: list[Any] = []
        for result in results:
            candidates = result.get("eventIds", [result.get("_id")])
            for candidate in candidates:
                if candidate is not None and candidate not in identifiers:
                    identifiers.append(candidate)
        return identifiers or [current_id]

    def _insert_alert(self, rule: dict[str, Any], event: dict[str, Any], results: list[dict[str, Any]]) -> bool:
        created = datetime.now(timezone.utc)
        inserted_at = event.get("eventInsertedAt", created)
        if inserted_at.tzinfo is None:
            inserted_at = inserted_at.replace(tzinfo=timezone.utc)
        cooldown = int(rule.get("cooldownSeconds", 300))
        bucket = int(event["ts"].replace(tzinfo=timezone.utc).timestamp()) // cooldown
        dedupe_source = f"{rule['ruleId']}|{event['srcIp']}|{event['deviceId']}|{bucket}"
        dedupe_key = hashlib.sha256(dedupe_source.encode()).hexdigest()
        device = self.db.devices.find_one({"deviceId": event["deviceId"]}, {"ip": 1}) or {}
        alert = {
            "ts": event["ts"],
            "ruleId": rule["ruleId"],
            "deviceId": event["deviceId"],
            "actor": event["srcIp"],
            "targetIp": device.get("ip", event["deviceId"]),
            "stage": rule["stage"],
            "severity": rule["severity"],
            "eventIds": self._event_ids(results, event["_id"]),
            "eventInsertedAt": inserted_at,
            "alertCreatedAt": created,
            "detectionLatencyMs": max(0.0, (created - inserted_at).total_seconds() * 1_000),
            "dedupeKey": dedupe_key,
        }
        try:
            self.alerts.insert_one(alert)
            LOGGER.info("Alert %s for %s", rule["ruleId"], event["deviceId"])
            return True
        except DuplicateKeyError:
            return False

    def process_event(self, event: dict[str, Any]) -> int:
        with self._rules_lock:
            rules = list(self._rules)
        inserted = 0
        for rule in rules:
            try:
                results = self._evaluate(rule, event)
                if results and self._insert_alert(rule, event, results):
                    inserted += 1
            except PyMongoError:
                LOGGER.exception("Rule execution failed: %s", rule.get("ruleId"))
        return inserted

    def _resume_token(self) -> Any | None:
        state = self.state.find_one({"_id": RESUME_STATE_ID})
        return state.get("token") if state else None

    def run(self, max_events: int | None = None) -> int:
        self.start_rule_cache()
        options: dict[str, Any] = {"full_document": "default", "max_await_time_ms": 1_000}
        token = self._resume_token()
        if token:
            options["resume_after"] = token
        processed = 0
        pipeline = [{"$match": {"operationType": "insert"}}]
        try:
            with self.events.watch(pipeline, **options) as stream:
                while not self._stop.is_set():
                    change = stream.try_next()
                    if change is None:
                        continue
                    self.process_event(change["fullDocument"])
                    self.state.update_one(
                        {"_id": RESUME_STATE_ID},
                        {"$set": {"token": change["_id"], "lastEventId": change["fullDocument"]["_id"], "updatedAt": datetime.now(timezone.utc)}},
                        upsert=True,
                    )
                    processed += 1
                    if max_events is not None and processed >= max_events:
                        break
        finally:
            self.stop()
        return processed

    def stop(self) -> None:
        self._stop.set()
        if self._rule_thread and self._rule_thread.is_alive() and threading.current_thread() is not self._rule_thread:
            self._rule_thread.join(timeout=2)


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s %(message)s")
    client = MongoClient(detector_uri(), serverSelectionTimeoutMS=10_000)
    worker = Detector(client, os.getenv("MONGO_DATABASE", "honeygraph"), int(os.getenv("RULE_MAX_TIME_MS", "2000")))
    signal.signal(signal.SIGTERM, lambda *_: worker.stop())
    signal.signal(signal.SIGINT, lambda *_: worker.stop())
    try:
        worker.run()
    finally:
        client.close()


if __name__ == "__main__":
    main()
