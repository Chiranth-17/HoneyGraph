from fastapi import APIRouter, Query, Request

from app.api_models import PageResponse
from app.auth import CurrentUser
from app.serializers import json_value, page

router = APIRouter(prefix="/api/devices", tags=["devices"])


@router.get("", response_model=PageResponse)
def devices(request: Request, user: CurrentUser, pageNumber: int = Query(1, ge=1), pageSize: int = Query(50, ge=1, le=500)) -> dict:
    return page(request.app.state.db.devices, {}, pageNumber, pageSize, [("deviceId", 1)])


@router.get("/near", response_model=list[dict])
def near(request: Request, user: CurrentUser, lng: float, lat: float, radius: float = Query(gt=0, le=100000)) -> list[dict]:
    query = {"location": {"$near": {"$geometry": {"type": "Point", "coordinates": [lng, lat]}, "$maxDistance": radius}}}
    return json_value(list(request.app.state.db.devices.find(query).limit(500)))


@router.get("/{device_id}/timeline", response_model=PageResponse)
def timeline(device_id: str, request: Request, user: CurrentUser, pageNumber: int = Query(1, ge=1), pageSize: int = Query(100, ge=1, le=500)) -> dict:
    return page(request.app.state.db.events, {"deviceId": device_id}, pageNumber, pageSize, [("ts", -1)])
