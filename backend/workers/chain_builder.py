"""Reconstruct connected alert chains and commit incidents atomically."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
from pymongo.client_session import ClientSession
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from workers.detector import detector_uri
from workers.risk_scorer import calculate_risks, upsert_risks

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


class ChainBuilder:
    """Use bidirectional graph lookups, then atomically materialize an incident."""

    def __init__(self, client: MongoClient, database: str, window_seconds: int = 900, alert_ids: list[ObjectId] | None = None) -> None:
        self.client = client
        self.db = client[database]
        self.window_seconds = window_seconds
        self.alert_ids = alert_ids
        self._closed_ids: list[ObjectId] = []

    def _restriction(self, start: datetime, end: datetime) -> dict[str, Any]:
        match: dict[str, Any] = {"ts": {"$gte": start, "$lte": end}}
        if self.alert_ids is not None:
            match["_id"] = {"$in": self.alert_ids}
        if self._closed_ids:
            match["incidentId"] = {"$nin": self._closed_ids}
        return match

    def _bounds(self, seed: dict[str, Any]) -> tuple[datetime, datetime]:
        return seed["ts"] - timedelta(seconds=self.window_seconds), seed["ts"] + timedelta(seconds=self.window_seconds)

    def _root(self, alert_id: ObjectId) -> dict[str, Any]:
        seed = self.db.alerts.find_one({"_id": alert_id})
        if not seed:
            raise ValueError(f"alert {alert_id} does not exist")
        start, end = self._bounds(seed)
        pipeline = [
            {"$match": {"_id": alert_id}},
            {"$graphLookup": {
                "from": "alerts", "startWith": "$actor", "connectFromField": "actor",
                "connectToField": "targetIp", "as": "ancestors", "maxDepth": 5,
                "depthField": "reverseHop", "restrictSearchWithMatch": self._restriction(start, seed["ts"]),
            }},
        ]
        result = next(iter(self.db.alerts.aggregate(pipeline)))
        candidates = [result, *result.get("ancestors", [])]
        # An incoming cycle must not move the root past the earliest observation.
        return min(candidates, key=lambda item: (item["ts"], str(item["_id"])))

    def reconstruct(self, alert_id: ObjectId) -> list[dict[str, Any]]:
        self._closed_ids = self.db.incidents.distinct("_id", {"status": "closed"})
        root = self._root(alert_id)
        start, end = self._bounds(root)
        pipeline = [
            # Parallel detections from one source (brute-force stages or scan
            # targets) belong together as well as actor-to-target hop chains.
            {"$match": {**self._restriction(start, end), "actor": root["actor"]}},
            {"$graphLookup": {
                "from": "alerts", "startWith": "$targetIp", "connectFromField": "targetIp",
                "connectToField": "actor", "as": "descendants", "maxDepth": 5,
                "depthField": "graphHop", "restrictSearchWithMatch": self._restriction(start, end),
            }},
        ]
        unique: dict[ObjectId, dict[str, Any]] = {}
        for result in self.db.alerts.aggregate(pipeline):
            chain = [{**result, "hop": 0}, *[
                {**item, "hop": item.get("graphHop", 0) + 1}
                for item in result.get("descendants", [])
            ]]
            # Graph traversal is native MongoDB; only minimum-depth ordering
            # and removal of duplicate returned documents happen here.
            for item in chain:
                current = unique.get(item["_id"])
                if current is None or item["hop"] < current["hop"]:
                    unique[item["_id"]] = item
        return sorted(unique.values(), key=lambda item: (item["hop"], item["ts"], str(item["_id"])))

    @staticmethod
    def _key(chain: list[dict[str, Any]]) -> str:
        material = "|".join(sorted(str(item["_id"]) for item in chain))
        return hashlib.sha256(material.encode()).hexdigest()

    @staticmethod
    def _embedded(chain: list[dict[str, Any]]) -> list[dict[str, Any]]:
        fields = ("alertId", "hop", "ts", "ruleId", "deviceId", "actor", "targetIp", "stage", "severity")
        return [
            {key: (item["_id"] if key == "alertId" else item[key]) for key in fields}
            for item in chain
        ]

    def build(self, alert_id: ObjectId, failpoint: Callable[[], None] | None = None) -> ObjectId:
        seed = self.db.alerts.find_one({"_id": alert_id}, {"incidentId": 1})
        if seed and seed.get("incidentId"):
            closed = self.db.incidents.find_one({"_id": seed["incidentId"], "status": "closed"}, {"_id": 1})
            if closed:
                return closed["_id"]  # Closed investigations remain immutable here.
        chain = self.reconstruct(alert_id)
        if not chain:
            raise ValueError("no alerts available for this incident")
        chain_key = self._key(chain)
        alert_ids = [item["_id"] for item in chain]
        device_ids = [item["deviceId"] for item in chain]
        now = datetime.now(timezone.utc)

        def transaction(session: ClientSession) -> ObjectId:
            existing = self.db.incidents.find_one({"chainKey": chain_key}, session=session)
            if not existing:
                existing = self.db.incidents.find_one(
                    {"status": {"$in": ["open", "triaged"]}, "chain.alertId": {"$in": alert_ids}},
                    sort=[("createdAt", 1)], session=session,
                )
            if existing:
                incident_id = existing["_id"]
                combined = {item["alertId"]: item for item in existing.get("chain", [])}
                combined.update({item["alertId"]: item for item in self._embedded(chain)})
                embedded = sorted(combined.values(), key=lambda item: (item["hop"], item["ts"], str(item["alertId"])))
                self.db.incidents.update_one(
                    {"_id": incident_id},
                    {"$set": {"chain": embedded, "updatedAt": now}}, session=session,
                )
            else:
                incident_id = ObjectId()
                self.db.incidents.insert_one({
                    "_id": incident_id, "chainKey": chain_key, "status": "open", "createdAt": now,
                    "updatedAt": now, "statusHistory": [{"status": "open", "ts": now}],
                    "chain": self._embedded(chain),
                }, session=session)
            self.db.alerts.update_many({"_id": {"$in": alert_ids}}, {"$set": {"incidentId": incident_id}}, session=session)
            if failpoint:
                failpoint()
            score_devices = sorted({item["deviceId"] for item in embedded}) if existing else device_ids
            upsert_risks(self.db, calculate_risks(self.db, score_devices, as_of=now, session=session), session=session)
            return incident_id

        for attempt in range(3):
            try:
                with self.client.start_session() as session:
                    return session.with_transaction(
                        transaction, read_concern=ReadConcern("snapshot"), write_concern=WriteConcern("majority")
                    )
            except DuplicateKeyError:
                if attempt == 2:
                    raise
        raise RuntimeError("incident transaction retry limit reached")


def main() -> None:
    with MongoClient(detector_uri(), serverSelectionTimeoutMS=10_000) as client:
        builder = ChainBuilder(client, os.getenv("MONGO_DATABASE", "honeygraph"))
        for alert in builder.db.alerts.find({"incidentId": {"$exists": False}}, {"_id": 1}).sort("ts", 1):
            builder.build(alert["_id"])


if __name__ == "__main__":
    main()

