"""Phase 6 exact-position tamper and checkpoint tests."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from dotenv import load_dotenv
from pymongo import MongoClient

from app.hashchain import GENESIS_HASH, compute_hash
from workers.integrity_checker import TamperDemo, check_device, compare_checkpoint, export_checkpoint, tamper_uri

load_dotenv()


@pytest.fixture()
def chain(request):
    device_id = f"integrity-{request.node.name}"
    with MongoClient(os.environ["MONGODB_URI"]) as admin:
        db = admin[os.getenv("MONGO_DATABASE", "honeygraph")]
        previous = GENESIS_HASH
        start = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=1)
        documents = []
        for index in range(1, 7):
            event = {
                "ts": start + timedelta(seconds=index), "deviceId": device_id, "protocol": "ssh",
                "eventType": "login_failed", "srcIp": "192.0.2.90",
                "geo": {"type": "Point", "coordinates": [77.59, 12.97]},
                "payload": {"user": "demo", "attempts": index}, "prevHash": previous,
                "chainSeq": index, "eventInsertedAt": start, "ingestBatchId": "integrity-test",
            }
            event["hash"] = compute_hash(previous, event)
            previous = event["hash"]
            documents.append(event)
        ids = db.events.insert_many(documents).inserted_ids
        yield db, device_id, documents, ids
        db.events.delete_many({"deviceId": device_id})
        db.system_state.delete_one({"_id": "integrity.checkpoint.latest"})


def demo() -> tuple[MongoClient, TamperDemo]:
    client = MongoClient(tamper_uri())
    return client, TamperDemo(client[os.getenv("MONGO_DATABASE", "honeygraph")])


def test_clean_chain_has_no_break(chain):
    db, device_id, _, _ = chain
    assert check_device(db, device_id) is None


def test_modified_event_reports_exact_position(chain):
    db, device_id, _, ids = chain
    client, helper = demo()
    try:
        assert helper.edit(ids[2]) == 1
    finally:
        client.close()
    broken = check_device(db, device_id)
    assert (broken.reason, broken.position) == ("modified", 3)


def test_deleted_middle_event_reports_exact_position(chain):
    db, device_id, _, ids = chain
    client, helper = demo()
    try:
        assert helper.delete(ids[2]) == 1
    finally:
        client.close()
    broken = check_device(db, device_id)
    assert (broken.reason, broken.position) == ("missing", 3)


def test_swapped_events_report_exact_position(chain):
    db, device_id, documents, ids = chain
    client, helper = demo()
    try:
        assert helper.swap(ids[2], documents[2]["ts"], ids[3], documents[3]["ts"]) == 2
    finally:
        client.close()
    broken = check_device(db, device_id)
    assert (broken.reason, broken.position) == ("reordered", 3)


def test_checkpoint_detects_tail_truncation(chain, tmp_path):
    db, device_id, _, ids = chain
    checkpoint = export_checkpoint(db, tmp_path, device_ids=[device_id])
    client, helper = demo()
    try:
        assert helper.delete(ids[-1]) == 1
    finally:
        client.close()
    broken = compare_checkpoint(db, checkpoint)
    assert len(broken) == 1
    assert (broken[0].reason, broken[0].position) == ("truncated", 6)
