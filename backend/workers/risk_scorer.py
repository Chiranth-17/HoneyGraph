"""MongoDB-native exponentially decayed device risk scoring."""

from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from pymongo.client_session import ClientSession
from pymongo.database import Database


def risk_pipeline(device_ids: Iterable[str], as_of: datetime, half_life_hours: float) -> list[dict[str, Any]]:
    """Build the single aggregation used to score all requested devices."""
    if half_life_hours <= 0:
        raise ValueError("risk half-life must be positive")
    now = as_of.astimezone(timezone.utc)
    decay_lambda = math.log(2) / half_life_hours
    return [
        {"$match": {"deviceId": {"$in": sorted(set(device_ids))}, "ts": {"$gte": now - timedelta(hours=24), "$lte": now}}},
        {"$set": {"ageHours": {"$divide": [{"$dateDiff": {"startDate": "$ts", "endDate": now, "unit": "minute"}}, 60]}}},
        {"$set": {"contribution": {"$multiply": ["$severity", {"$exp": {"$multiply": [-decay_lambda, "$ageHours"]}}]}}},
        {"$sort": {"contribution": -1, "ts": -1}},
        {"$group": {
            "_id": "$deviceId",
            "total": {"$sum": "$contribution"},
            "factors": {"$push": {"alertId": "$_id", "ruleId": "$ruleId", "severity": "$severity", "contribution": "$contribution", "ts": "$ts"}},
        }},
        {"$project": {"_id": 0, "deviceId": "$_id", "score": {"$min": [100, "$total"]}, "factors": {"$slice": ["$factors", 5]}, "calculatedAt": {"$literal": now}}},
    ]


def calculate_risks(
    db: Database[Any], device_ids: Iterable[str], *, as_of: datetime | None = None,
    half_life_hours: float | None = None, session: ClientSession | None = None,
) -> list[dict[str, Any]]:
    """Calculate scores in MongoDB; callers decide where/when to persist them."""
    ids = sorted(set(device_ids))
    if not ids:
        return []
    moment = as_of or datetime.now(timezone.utc)
    half_life = half_life_hours or float(os.getenv("RISK_HALF_LIFE_HOURS", "6"))
    return list(db.alerts.aggregate(risk_pipeline(ids, moment, half_life), session=session))


def upsert_risks(db: Database[Any], scores: list[dict[str, Any]], session: ClientSession | None = None) -> None:
    for score in scores:
        db.risk_scores.replace_one({"deviceId": score["deviceId"]}, score, upsert=True, session=session)

