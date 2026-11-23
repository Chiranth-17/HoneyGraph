"""Pluggable event sinks for the simulator."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from copy import deepcopy
from typing import Any
from urllib.parse import quote_plus

import httpx
from bson import ObjectId
from pymongo import MongoClient

from .models import ZERO_HASH, chained_hash


def service_uri(username: str, password: str) -> str:
    port = os.getenv("MONGO1_PORT", "27017")
    database = os.getenv("MONGO_DATABASE", "honeygraph")
    return (
        f"mongodb://{quote_plus(username)}:{quote_plus(password)}@localhost:{port}/{database}"
        f"?authSource={database}&replicaSet=rs0&directConnection=true"
    )


class EventSink(ABC):
    @abstractmethod
    def write(self, events: list[dict[str, Any]]) -> list[ObjectId]:
        """Write events and return their identifiers in input order."""


class MemorySink(EventSink):
    """Test sink that records events without external I/O."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def write(self, events: list[dict[str, Any]]) -> list[ObjectId]:
        copied = deepcopy(events)
        ids = [ObjectId() for _ in copied]
        for item, identifier in zip(copied, ids, strict=True):
            item["_id"] = identifier
        self.events.extend(copied)
        return ids


class DirectMongoSink(EventSink):
    """Temporary Phase 2 sink using only the ingest service's narrow grants."""

    def __init__(self, batch_size: int = 1_000) -> None:
        self.client: MongoClient[dict[str, Any]] = MongoClient(
            service_uri("ingest_svc", os.environ["MONGO_INGEST_PASSWORD"]), serverSelectionTimeoutMS=10_000
        )
        self.events = self.client[os.getenv("MONGO_DATABASE", "honeygraph")].events
        self.batch_size = batch_size

    def close(self) -> None:
        self.client.close()

    def _stored_heads(self, device_ids: set[str]) -> dict[str, str]:
        heads: dict[str, str] = {}
        for device_id in device_ids:
            latest = self.events.find_one({"deviceId": device_id}, sort=[("_id", -1)], projection={"hash": 1})
            heads[device_id] = latest["hash"] if latest else ZERO_HASH
        return heads

    def write(self, events: list[dict[str, Any]]) -> list[ObjectId]:
        if not events:
            return []
        heads = self._stored_heads({event["deviceId"] for event in events})
        documents: list[dict[str, Any]] = []
        for source in events:
            event = deepcopy(source)
            previous = heads[event["deviceId"]]
            event["prevHash"] = previous
            event["hash"] = chained_hash(previous, event)
            heads[event["deviceId"]] = event["hash"]
            documents.append(event)
        inserted: list[ObjectId] = []
        for start in range(0, len(documents), self.batch_size):
            result = self.events.insert_many(documents[start : start + self.batch_size], ordered=True)
            inserted.extend(result.inserted_ids)
        return inserted


class ApiSink(EventSink):
    """POST events to the future FastAPI ingestion endpoint."""

    def __init__(self, base_url: str, batch_size: int = 5_000) -> None:
        self.client = httpx.Client(base_url=base_url, timeout=30)
        self.batch_size = batch_size

    def close(self) -> None:
        self.client.close()

    def write(self, events: list[dict[str, Any]]) -> list[ObjectId]:
        identifiers: list[ObjectId] = []
        payloads: list[dict[str, Any]] = []
        for event in events:
            payload = {key: deepcopy(value) for key, value in event.items() if key not in {"prevHash", "hash", "eventInsertedAt", "chainSeq", "ingestBatchId", "_id"}}
            payload["ts"] = payload["ts"].isoformat()
            payloads.append(payload)
        for start in range(0, len(payloads), self.batch_size):
            response = self.client.post("/api/ingest", json=payloads[start : start + self.batch_size])
            response.raise_for_status()
            identifiers.extend(ObjectId(item["id"]) for item in response.json()["events"])
        return identifiers

