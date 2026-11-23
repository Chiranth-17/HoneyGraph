from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query, Request

from app.api_models import PageResponse, StatusRequest
from app.auth import CurrentUser
from app.serializers import json_value, page

router = APIRouter(prefix="/api/incidents", tags=["incidents"])
NEXT = {"open": "triaged", "triaged": "closed"}


def oid(value: str) -> ObjectId:
    try: return ObjectId(value)
    except Exception as exc: raise HTTPException(404, "incident not found") from exc


@router.get("", response_model=PageResponse)
def list_incidents(request: Request, user: CurrentUser, pageNumber: int = Query(1, ge=1), pageSize: int = Query(50, ge=1, le=500)) -> dict:
    return page(request.app.state.db.incidents, {}, pageNumber, pageSize, [("updatedAt", -1)])


@router.get("/{incident_id}", response_model=dict)
def detail(incident_id: str, request: Request, user: CurrentUser) -> dict:
    item = request.app.state.db.incidents.find_one({"_id": oid(incident_id)})
    if not item: raise HTTPException(404, "incident not found")
    return json_value(item)


@router.patch("/{incident_id}/status", response_model=dict)
def transition(incident_id: str, body: StatusRequest, request: Request, user: CurrentUser) -> dict:
    identifier = oid(incident_id)
    item = request.app.state.db.incidents.find_one({"_id": identifier})
    if not item: raise HTTPException(404, "incident not found")
    if NEXT.get(item.get("status", "open")) != body.status:
        raise HTTPException(409, detail=f"invalid transition {item.get('status', 'open')} -> {body.status}")
    at = datetime.now(timezone.utc)
    result = request.app.state.db.incidents.update_one(
        {"_id": identifier, "status": item.get("status", "open")},
        {"$set": {"status": body.status, "updatedAt": at}, "$push": {"statusHistory": {"status": body.status, "ts": at, "by": user["username"]}}},
    )
    if not result.matched_count:
        raise HTTPException(409, "incident status changed; refresh before trying again")
    return json_value(request.app.state.db.incidents.find_one({"_id": identifier}))
