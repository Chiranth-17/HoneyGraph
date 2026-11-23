from fastapi import APIRouter, HTTPException, Request

from app.auth import CurrentUser
from app.serializers import json_value

router = APIRouter(prefix="/api/risk", tags=["risk"])


@router.get("", response_model=list[dict])
def all_risk(request: Request, user: CurrentUser) -> list[dict]:
    return json_value(list(request.app.state.db.risk_scores.find().sort("score", -1)))


@router.get("/{device_id}", response_model=dict)
def one_risk(device_id: str, request: Request, user: CurrentUser) -> dict:
    item = request.app.state.db.risk_scores.find_one({"deviceId": device_id})
    if not item: raise HTTPException(404, "risk score not found")
    return json_value(item)
