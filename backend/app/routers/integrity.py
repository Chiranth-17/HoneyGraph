from datetime import datetime, timedelta, timezone
from uuid import uuid4

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request

from app.api_models import IntegrityRequest, TamperRequest
from app.auth import AdminUser, CurrentUser
from app.schemas import IngestEvent
from app.serializers import json_value
from workers.integrity_checker import TamperDemo, check_all

router = APIRouter(prefix="/api/integrity", tags=["integrity"])


@router.post("/tamper-demo", response_model=dict)
async def tamper_demo(request: Request, user: AdminUser) -> dict:
    """Create three isolated chains and apply edit, delete, and reorder mutations."""
    stamp = uuid4().hex[:10]
    origin = datetime.now(timezone.utc).replace(microsecond=0)
    devices = {action: f"tamper-{action}-{stamp}" for action in ("edit", "delete", "swap")}
    inserted: dict[str, list[ObjectId]] = {}
    for action, device_id in devices.items():
        batch = [IngestEvent.model_validate({
            "ts": origin + timedelta(milliseconds=100 * index), "deviceId": device_id,
            "protocol": "ssh", "eventType": "login_failed", "srcIp": "192.0.2.250",
            "geo": {"type": "Point", "coordinates": [77.59, 12.97]},
            "payload": {"user": "integrity-demo", "attempts": index},
        }) for index in range(1, 7)]
        result = await request.app.state.ingestion.ingest(batch)
        inserted[action] = [ObjectId(item["id"]) for item in result]

    helper = TamperDemo(request.app.state.tamper_db)
    helper.edit(inserted["edit"][2])
    helper.delete(inserted["delete"][2])
    first, second = inserted["swap"][2:4]
    events = {item["_id"]: item for item in request.app.state.db.events.find({"_id": {"$in": [first, second]}}, {"ts": 1})}
    helper.swap(first, events[first]["ts"], second, events[second]["ts"])
    return {"devices": devices, "actions": ["edit", "delete", "swap"]}


@router.post("/check", response_model=dict)
def run_check(body: IntegrityRequest, request: Request, user: CurrentUser) -> dict:
    breaks, events, elapsed = check_all(request.app.state.db, body.deviceId, reporter=None)
    result = {"checkedAt": datetime.now(timezone.utc), "deviceId": body.deviceId, "events": events, "seconds": elapsed, "breaks": [item.__dict__ for item in breaks]}
    request.app.state.db.system_state.replace_one({"_id": "integrity.api.latest"}, {"_id": "integrity.api.latest", **result}, upsert=True)
    return json_value(result)


@router.get("/results", response_model=dict)
def results(request: Request, user: CurrentUser) -> dict:
    item = request.app.state.db.system_state.find_one({"_id": "integrity.api.latest"})
    return json_value(item or {"breaks": [], "events": 0})


@router.post("/tamper", response_model=dict)
def tamper(body: TamperRequest, request: Request, user: AdminUser) -> dict:
    try: ids = [ObjectId(value) for value in body.eventIds]
    except Exception as exc: raise HTTPException(422, "invalid event ObjectId") from exc
    helper = TamperDemo(request.app.state.tamper_db)
    if body.action == "edit" and len(ids) == 1: changed = helper.edit(ids[0])
    elif body.action == "delete" and len(ids) == 1: changed = helper.delete(ids[0])
    elif body.action == "swap" and len(ids) == 2:
        events = list(request.app.state.db.events.find({"_id": {"$in": ids}}, {"ts": 1}))
        by_id = {item["_id"]: item for item in events}
        if len(by_id) != 2: raise HTTPException(404, "event not found")
        changed = helper.swap(ids[0], by_id[ids[0]]["ts"], ids[1], by_id[ids[1]]["ts"])
    else: raise HTTPException(422, "action requires one event ID, or two for swap")
    return {"action": body.action, "changed": changed}
