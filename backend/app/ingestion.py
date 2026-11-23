"""Concurrency-safe, transaction-backed event ingestion service."""

from __future__ import annotations

import asyncio
import inspect
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from uuid import uuid4

from bson import ObjectId
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.write_concern import WriteConcern

from .hashchain import GENESIS_HASH, compute_hash, utc_timestamp
from .schemas import IngestEvent

FailureHook = Callable[[list[dict[str, Any]]], None | Awaitable[None]]


class IngestionService:
    """Serialize each device chain while allowing different devices per bulk."""

    def __init__(self, client: MongoClient, database: str) -> None:
        self.client = client
        self.events: Collection = client[database].events.with_options(write_concern=WriteConcern(w=1))
        self._heads: dict[str, tuple[str, int]] = {}
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.failure_hook: FailureHook | None = None

    def _load_head(self, device_id: str) -> tuple[str, int]:
        latest = self.events.find_one(
            {"deviceId": device_id},
            sort=[("_id", -1)],
            projection={"hash": 1, "chainSeq": 1},
        )
        if not latest:
            return GENESIS_HASH, 0
        return latest["hash"], int(latest.get("chainSeq", 0))

    def _commit(self, documents: list[dict[str, Any]]) -> list[ObjectId]:
        """Use a transaction so unordered bulk failure cannot persist a prefix."""
        with self.client.start_session() as session:
            with session.start_transaction(write_concern=WriteConcern(w=1)):
                result = self.events.insert_many(documents, ordered=False, session=session)
                if self.failure_hook:
                    hook_result = self.failure_hook(documents)
                    if inspect.isawaitable(hook_result):
                        raise RuntimeError("asynchronous failure hooks are not supported inside the DB worker")
                return result.inserted_ids

    async def ingest(self, events: list[IngestEvent]) -> list[dict[str, str]]:
        if not events:
            raise ValueError("batch must contain at least one event")
        if len(events) > 5_000:
            raise ValueError("batch exceeds the 5,000 event limit")

        device_ids = sorted({event.deviceId for event in events})
        locks = [self._locks[device_id] for device_id in device_ids]
        for lock in locks:
            await lock.acquire()
        try:
            missing = [device_id for device_id in device_ids if device_id not in self._heads]
            loaded = await asyncio.gather(*(asyncio.to_thread(self._load_head, device_id) for device_id in missing))
            for device_id, head in zip(missing, loaded, strict=True):
                self._heads[device_id] = head

            confirmed = {device_id: self._heads[device_id] for device_id in device_ids}
            working = dict(confirmed)
            inserted_at = datetime.now(timezone.utc)
            batch_id = uuid4().hex
            documents: list[dict[str, Any]] = []
            for event in events:
                previous, sequence = working[event.deviceId]
                document = event.model_dump(mode="python")
                document["ts"] = utc_timestamp(document["ts"])
                document["geo"]["coordinates"] = list(document["geo"]["coordinates"])
                document["prevHash"] = previous
                document["chainSeq"] = sequence + 1
                document["eventInsertedAt"] = inserted_at
                document["ingestBatchId"] = batch_id
                document["hash"] = compute_hash(previous, document)
                working[event.deviceId] = (document["hash"], sequence + 1)
                documents.append(document)
            try:
                identifiers = await asyncio.to_thread(self._commit, documents)
            except Exception:
                for device_id, head in confirmed.items():
                    self._heads[device_id] = head
                raise
            for device_id in device_ids:
                self._heads[device_id] = working[device_id]
            return [{"id": str(identifier), "hash": document["hash"]} for identifier, document in zip(identifiers, documents, strict=True)]
        finally:
            for lock in reversed(locks):
                lock.release()

    def clear_cache(self) -> None:
        self._heads.clear()

