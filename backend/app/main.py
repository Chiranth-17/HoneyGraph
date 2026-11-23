"""HoneyGraph FastAPI application."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pymongo.errors import PyMongoError

from .db import api_client, ingest_client, service_uri
from .ingestion import IngestionService
from .schemas import IngestEvent


@asynccontextmanager
async def lifespan(app: FastAPI):
    database = os.getenv("MONGO_DATABASE", "honeygraph")
    client = ingest_client()
    api = api_client()
    rule = __import__("pymongo").MongoClient(service_uri("rule_admin", os.environ["MONGO_RULE_ADMIN_PASSWORD"]))
    tamper = __import__("pymongo").MongoClient(service_uri("tamper_demo", os.environ["MONGO_TAMPER_PASSWORD"]))
    client.admin.command("ping")
    app.state.ingestion = IngestionService(client, database)
    app.state.db = api[database]
    app.state.rule_db = rule[database]
    app.state.tamper_db = tamper[database]
    app.state.scenario_jobs = {}
    app.state.scenario_tasks = {}
    yield
    for task in app.state.scenario_tasks.values():
        if not task.done(): task.cancel()
    client.close(); api.close(); rule.close(); tamper.close()


app = FastAPI(
    title="HoneyGraph Threat Intelligence API", version="0.7.0", lifespan=lifespan,
    description="Authenticated REST and WebSocket API for the HoneyGraph defensive IoT simulation.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/ingest", status_code=201)
async def ingest(request: Request, payload: IngestEvent | list[IngestEvent] = Body(...)) -> dict[str, Any]:
    events = payload if isinstance(payload, list) else [payload]
    if not events:
        raise HTTPException(status_code=422, detail="batch must contain at least one event")
    if len(events) > 5_000:
        raise HTTPException(status_code=413, detail="batch exceeds the 5,000 event limit")
    try:
        inserted = await request.app.state.ingestion.ingest(events)
    except PyMongoError as exc:
        raise HTTPException(status_code=503, detail="event batch was not committed") from exc
    return {"inserted": len(inserted), "events": inserted}


from .routers import alerts, auth, devices, incidents, integrity, risk, rules, scenarios, stats, users  # noqa: E402
from .ws import router as ws_router  # noqa: E402

for api_router in (auth.router, alerts.router, incidents.router, devices.router, risk.router, rules.router, integrity.router, users.router, scenarios.router, stats.router, ws_router):
    app.include_router(api_router)

