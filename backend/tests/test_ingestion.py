"""Phase 3 integration tests for API validation and hash-chain integrity."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest
from dotenv import load_dotenv
from pymongo import MongoClient

from app.db import ingest_client
from app.hashchain import GENESIS_HASH, verify_link
from app.ingestion import IngestionService
from app.main import app
from app.schemas import IngestEvent

load_dotenv()
DB_NAME = os.getenv("MONGO_DATABASE", "honeygraph")


def event(device_id: str, sequence: int = 0) -> dict[str, Any]:
    return {
        "ts": datetime(2026, 10, 14, 12, 0, sequence, 123456, tzinfo=timezone.utc).isoformat(),
        "deviceId": device_id,
        "protocol": "mqtt",
        "eventType": "mqtt_publish",
        "srcIp": "10.42.10.10",
        "geo": {"type": "Point", "coordinates": [77.5946, 12.9716]},
        "payload": {"topic": "sensors/test", "clientId": device_id, "action": "publish"},
    }


@pytest.fixture
def service() -> IngestionService:
    client = ingest_client()
    instance = IngestionService(client, DB_NAME)
    yield instance
    client.close()


@pytest.fixture
def root_client() -> MongoClient:
    client = MongoClient(os.environ["MONGODB_URI"])
    yield client
    client.close()


def _clean(root_client: MongoClient, device_id: str) -> None:
    root_client[DB_NAME].events.delete_many({"deviceId": device_id})


def _verify(documents: list[dict[str, Any]]) -> None:
    previous = GENESIS_HASH
    for sequence, document in enumerate(documents, start=1):
        assert document["chainSeq"] == sequence
        assert verify_link(document, previous)
        assert document["eventInsertedAt"].tzinfo is None  # BSON stores UTC datetimes without tzinfo by default.
        previous = document["hash"]


@pytest.mark.asyncio
async def test_chain_continuity_across_batches(service: IngestionService, root_client: MongoClient) -> None:
    device_id = "phase3-continuity"
    _clean(root_client, device_id)
    await service.ingest([IngestEvent.model_validate(event(device_id, 0)), IngestEvent.model_validate(event(device_id, 1))])
    await service.ingest([IngestEvent.model_validate(event(device_id, 2)), IngestEvent.model_validate(event(device_id, 3))])
    documents = list(root_client[DB_NAME].events.find({"deviceId": device_id}).sort("chainSeq", 1))
    assert len(documents) == 4
    _verify(documents)


@pytest.mark.asyncio
async def test_concurrent_http_clients_do_not_fork_same_device(service: IngestionService, root_client: MongoClient) -> None:
    device_id = "phase3-concurrent"
    _clean(root_client, device_id)
    service.clear_cache()
    app.state.ingestion = service
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        requests = [client.post("/api/ingest", json=[event(device_id, client_id * 5 + offset) for offset in range(5)]) for client_id in range(8)]
        responses = await asyncio.gather(*requests)
    assert all(response.status_code == 201 for response in responses)
    documents = list(root_client[DB_NAME].events.find({"deviceId": device_id}).sort("chainSeq", 1))
    assert len(documents) == 40
    _verify(documents)


@pytest.mark.asyncio
async def test_invalid_payload_has_clear_validation_error(service: IngestionService) -> None:
    app.state.ingestion = service
    invalid = event("phase3-invalid")
    invalid["payload"] = {"topic": "missing-required-fields"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/ingest", json=invalid)
    assert response.status_code == 422
    details = response.json()["detail"]
    assert details
    assert any("payload" in ".".join(str(part) for part in item["loc"]) for item in details)


@pytest.mark.asyncio
async def test_partial_failure_aborts_batch_and_restores_cache(service: IngestionService, root_client: MongoClient) -> None:
    device_id = "phase3-partial-failure"
    _clean(root_client, device_id)
    service.clear_cache()

    def fail_after_insert(_: list[dict[str, Any]]) -> None:
        raise RuntimeError("simulated failure after server insert, before commit")

    service.failure_hook = fail_after_insert
    with pytest.raises(RuntimeError, match="simulated failure"):
        await service.ingest([IngestEvent.model_validate(event(device_id, index)) for index in range(3)])
    assert root_client[DB_NAME].events.count_documents({"deviceId": device_id}) == 0

    service.failure_hook = None
    await service.ingest([IngestEvent.model_validate(event(device_id, 4))])
    stored = root_client[DB_NAME].events.find_one({"deviceId": device_id})
    assert stored is not None
    assert stored["chainSeq"] == 1
    assert stored["prevHash"] == GENESIS_HASH
    assert verify_link(stored, GENESIS_HASH)

