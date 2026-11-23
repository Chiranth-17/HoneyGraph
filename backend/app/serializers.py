"""BSON-safe API serialization and pagination helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId


def json_value(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).isoformat()
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_value(item) for item in value]
    return value


def page(collection: Any, query: dict[str, Any], number: int, size: int, sort: list[tuple[str, int]]) -> dict[str, Any]:
    total = collection.count_documents(query)
    items = list(collection.find(query).sort(sort).skip((number - 1) * size).limit(size))
    return {"items": json_value(items), "page": number, "pageSize": size, "total": total}
