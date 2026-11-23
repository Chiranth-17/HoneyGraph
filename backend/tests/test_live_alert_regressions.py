"""Regressions for current-time dashboard scenarios and late-arriving alerts."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from bson import ObjectId

from app.api_models import ScenarioRequest
from app.routers import alerts, scenarios


def test_dashboard_scenario_uses_current_timestamps(monkeypatch):
    """Live runs must not inherit the simulator's deterministic fixture date."""
    captured = []
    monkeypatch.setattr(scenarios, '_build_scenario_incidents', lambda *args: [])

    async def ingest(events):
        captured.extend(events)
        return [{"id": str(ObjectId())} for _ in events]

    app = SimpleNamespace(state=SimpleNamespace(
        scenario_jobs={"clock-test": {}},
        db=SimpleNamespace(devices=SimpleNamespace(find=lambda *args: [])),
        ingestion=SimpleNamespace(ingest=ingest),
    ))
    before = datetime.now(timezone.utc)
    asyncio.run(scenarios.execute(app, "clock-test", ScenarioRequest(name="mirai_bruteforce", seed=42)))
    after = datetime.now(timezone.utc)
    assert app.state.scenario_jobs["clock-test"]["status"] == "completed"
    assert captured
    assert all(before - timedelta(minutes=1) <= e.ts <= after for e in captured)
    assert [e.ts for e in captured] == sorted(e.ts for e in captured)


def test_alert_feed_orders_by_detection_time(monkeypatch):
    """Newly detected backfilled events must appear in the latest-alert feed."""
    observed = {}

    def capture_page(collection, query, number, size, sort):
        observed["sort"] = sort
        observed["query"] = query
        return {"items": [], "total": 0}

    monkeypatch.setattr(alerts, "page", capture_page)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=SimpleNamespace(alerts=object()))))
    alerts.list_alerts(request=request, user={}, device=None, eventType=None,
                       stage=None, start=None, end=None, pageNumber=1, pageSize=50)
    assert observed["sort"] == [("alertCreatedAt", -1), ("_id", -1)]
