from datetime import datetime

from fastapi import APIRouter, Query, Request

from app.api_models import PageResponse
from app.auth import CurrentUser
from app.serializers import page

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=PageResponse)
def list_alerts(
    request: Request, user: CurrentUser, device: str | None = None, eventType: str | None = None,
    stage: str | None = None, start: datetime | None = None, end: datetime | None = None,
    pageNumber: int = Query(1, ge=1), pageSize: int = Query(50, ge=1, le=500),
) -> dict:
    query: dict = {}
    if device: query["deviceId"] = device
    if stage: query["stage"] = stage
    if start or end:
        query["ts"] = {**({"$gte": start} if start else {}), **({"$lte": end} if end else {})}
    if eventType:
        ids = request.app.state.db.events.distinct("_id", {"eventType": eventType})
        query["eventIds"] = {"$in": ids}
    # Match the UI's "Detected" column and WebSocket arrival order. Backfilled
    # observations must not bury newly created alerts under older detections.
    return page(request.app.state.db.alerts, query, pageNumber, pageSize, [("alertCreatedAt", -1), ("_id", -1)])
