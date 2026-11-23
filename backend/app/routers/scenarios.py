import asyncio
import json
import os
import time
from datetime import datetime, timezone
from uuid import uuid4

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Request
from pymongo import MongoClient

from app.api_models import ScenarioRequest
from app.auth import AdminUser
from app.schemas import IngestEvent
from app.serializers import json_value
from simulator.run import generate
from workers.chain_builder import ChainBuilder

router = APIRouter(prefix="/api/scenarios", tags=["scenarios"])


def _processed_alerts(db, event_ids: list[str], name: str) -> list[dict]:
    """Wait for real change-stream processing, without creating any incident."""
    deadline = time.monotonic() + 20
    object_ids = [ObjectId(value) for value in event_ids]
    if not object_ids:
        return []
    processed = False
    while time.monotonic() < deadline:
        state = db.system_state.find_one({"_id": "detector.events.resume"}) or {}
        last = state.get("lastEventId")
        if isinstance(last, ObjectId) and last >= max(object_ids):
            processed = True
            break
        time.sleep(0.1)
    if not processed:
        raise RuntimeError("detector did not finish this batch within 20 seconds; check detector status")
    alerts = list(db.alerts.find({"eventIds": {"$in": object_ids}}).sort("ts", 1))
    if name == "lateral_movement":
        covered = {identifier for item in alerts if item["ruleId"] == "R-LATERAL-06" for identifier in item["eventIds"]}
        if not set(object_ids).issubset(covered):
            raise RuntimeError("not every lateral hop produced an alert; check the active rule or cooldown")
    return alerts


def _wait_for_scenario_alerts(event_ids: list[str], name: str) -> list[dict]:
    with MongoClient(os.environ["MONGO_DETECTOR_URI"], serverSelectionTimeoutMS=10_000) as client:
        return _processed_alerts(client[os.getenv("MONGO_DATABASE", "honeygraph")], event_ids, name)


def _build_scenario_incidents(event_ids: list[str], name: str) -> list[str]:
    """Correlate genuine batch alerts using graph lookups and a transaction."""
    with MongoClient(os.environ["MONGO_DETECTOR_URI"], serverSelectionTimeoutMS=10_000) as client:
        db = client[os.getenv("MONGO_DATABASE", "honeygraph")]
        alerts = _processed_alerts(db, event_ids, name)
        if not alerts:
            return []  # Disabled rules / absent baselines are not fabricated detections.
        builder = ChainBuilder(client, db.name, alert_ids=[item["_id"] for item in alerts])
        incident_ids: set[ObjectId] = set()
        handled: set[ObjectId] = set()
        for alert in alerts:
            if alert["_id"] in handled:
                continue
            incident_id = builder.build(alert["_id"])
            incident_ids.add(incident_id)
            row = db.incidents.find_one({"_id": incident_id}, {"chain.alertId": 1}) or {}
            handled.update(item["alertId"] for item in row.get("chain", []))
        return sorted(str(value) for value in incident_ids)


async def execute(app, job_id: str, body: ScenarioRequest) -> None:
    job = app.state.scenario_jobs[job_id]
    try:
        devices, events, _, counts = generate(500, 0, 0, [body.name], body.seed)
        # Pure simulator fixtures keep a deterministic date. Dashboard launches
        # represent live traffic: preserve relative timing, ending at the present,
        # so TTL retention and the risk window do not discard new observations.
        offset = datetime.now(timezone.utc) - max(event["ts"] for event in events)
        for event in events:
            event["ts"] += offset
        events.sort(key=lambda event: event["ts"])
        # Device IDs are stable across seeds, while generated IP assignments are not.
        # Rewrite internal actors to the persisted inventory so graph edges join exactly.
        generated_ip_to_id = {item["ip"]: item["deviceId"] for item in devices}
        stored_ips = {item["deviceId"]: item["ip"] for item in app.state.db.devices.find(
            {"deviceId": {"$in": [item["deviceId"] for item in devices]}}, {"deviceId": 1, "ip": 1}
        )}
        for event in events:
            actor_id = generated_ip_to_id.get(event["srcIp"])
            if actor_id in stored_ips:
                event["srcIp"] = stored_ips[actor_id]
        job["status"] = "running"
        inserted_ids: list[str] = []
        for start in range(0, len(events), 5000):
            result = await app.state.ingestion.ingest([
                IngestEvent.model_validate({key: value for key, value in item.items() if key not in {"prevHash", "hash"}})
                for item in events[start:start + 5000]
            ])
            inserted_ids.extend(item["id"] for item in result)
        job.update(status="detecting", counts=counts, insertedEventIds=inserted_ids, incidentIds=[], incidentId=None)
        if body.deferCorrelation:
            alerts = await asyncio.to_thread(_wait_for_scenario_alerts, inserted_ids, body.name)
            job.update(
                status="awaiting_correlation" if alerts else "completed", alertCount=len(alerts),
                message=None if alerts else "No new matching alerts; check rule activation, baseline or cooldown.",
            )
            return
        incident_ids = await asyncio.to_thread(_build_scenario_incidents, inserted_ids, body.name)
        job.update(
            status="completed", counts=counts, insertedEventIds=inserted_ids,
            incidentId=incident_ids[0] if incident_ids else None, incidentIds=incident_ids,
            message=None if incident_ids else "No new matching alerts; check rule activation, baseline or cooldown.",
            finishedAt=datetime.now(timezone.utc).isoformat(),
        )
    except asyncio.CancelledError:
        job["status"] = "stopped"
    except Exception as exc:
        job.update(status="failed", error=str(exc))


@router.post("/launch", status_code=202, response_model=dict)
async def launch(body: ScenarioRequest, request: Request, user: AdminUser) -> dict:
    job_id = uuid4().hex
    request.app.state.scenario_jobs[job_id] = {"id": job_id, "name": body.name, "seed": body.seed, "status": "queued", "deferCorrelation": body.deferCorrelation}
    task = asyncio.create_task(execute(request.app, job_id, body))
    request.app.state.scenario_tasks[job_id] = task
    return request.app.state.scenario_jobs[job_id]


@router.post("/{job_id}/correlate", response_model=dict)
async def correlate(job_id: str, request: Request, user: AdminUser) -> dict:
    job = request.app.state.scenario_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "scenario job not found")
    if not job.get("deferCorrelation"):
        raise HTTPException(409, "this run uses automatic correlation")
    if job["status"] == "completed" and job.get("incidentIds"):
        return job
    if job["status"] != "awaiting_correlation":
        raise HTTPException(409, "wait for matching alerts before building the incident")
    # Set before yielding: concurrent requests cannot start another builder.
    job.update(status="correlating", error=None)
    try:
        ids = await asyncio.to_thread(_build_scenario_incidents, job["insertedEventIds"], job["name"])
        job.update(status="completed", incidentIds=ids, incidentId=ids[0] if ids else None,
                   finishedAt=datetime.now(timezone.utc).isoformat())
    except Exception as exc:
        job.update(status="awaiting_correlation", error=str(exc))
        raise HTTPException(503, f"correlation failed; retry is safe: {exc}") from exc
    return job


@router.get("/{job_id}/evidence", response_model=dict)
def evidence(job_id: str, request: Request, user: AdminUser) -> dict:
    """Expose only database evidence linked to this launch, including Compass filters."""
    job = request.app.state.scenario_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "scenario job not found")
    db = request.app.state.db
    ids = [ObjectId(value) for value in job.get("insertedEventIds", [])]
    event_query = {"_id": {"$in": ids}}
    alert_query = {"eventIds": {"$in": ids}}
    alert_ids = db.alerts.distinct("_id", alert_query)
    incident_query = {"chain.alertId": {"$in": alert_ids}}
    def compass_filter(field: str, values: list[ObjectId]) -> str:
        return '{' + json.dumps(field) + ': {"$in": [' + ', '.join(f'ObjectId("{value}")' for value in values) + ']}}'
    return json_value({
        "events": list(db.events.find(event_query).sort("ts", 1).limit(200)),
        "alerts": list(db.alerts.find(alert_query).sort("ts", 1).limit(200)),
        "incidents": list(db.incidents.find(incident_query).limit(200)),
        "counts": {"events": db.events.count_documents(event_query), "alerts": db.alerts.count_documents(alert_query),
                   "incidents": db.incidents.count_documents(incident_query)},
        "compassFilters": {"events": compass_filter("_id", ids), "alerts": compass_filter("eventIds", ids),
                           "incidents": compass_filter("chain.alertId", alert_ids)},
    })


@router.post("/{job_id}/stop", response_model=dict)
async def stop(job_id: str, request: Request, user: AdminUser) -> dict:
    job = request.app.state.scenario_jobs.get(job_id)
    if not job: raise HTTPException(404, "scenario job not found")
    task = request.app.state.scenario_tasks.get(job_id)
    if task and not task.done(): task.cancel()
    job["status"] = "stopped"
    return job


@router.get("", response_model=list[dict])
def jobs(request: Request, user: AdminUser) -> list[dict]:
    return list(request.app.state.scenario_jobs.values())
