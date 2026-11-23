from fastapi import APIRouter, Request

from app.auth import CurrentUser
from app.serializers import json_value

router = APIRouter(prefix="/api/stats", tags=["statistics"])


@router.get("/dashboard", response_model=dict)
def dashboard(request: Request, user: CurrentUser) -> dict:
    db = request.app.state.db
    by_stage = list(db.alerts.aggregate([{"$group": {"_id": "$stage", "count": {"$sum": 1}}}, {"$sort": {"count": -1}}]))
    severity = list(db.alerts.aggregate([{"$group": {"_id": {"ts": {"$dateTrunc": {"date": "$ts", "unit": "hour"}}, "severity": "$severity"}, "count": {"$sum": 1}}}, {"$sort": {"_id.ts": 1}}]))
    risky = list(db.risk_scores.find().sort("score", -1).limit(10))
    return json_value({"alertsByStage": by_stage, "severityOverTime": severity, "topRiskyDevices": risky})
