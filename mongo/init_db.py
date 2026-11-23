"""Create HoneyGraph collections, validation, indexes, roles, and users.

The initializer is intentionally idempotent: collection creation is guarded,
validators and roles are updated in place, and indexes use stable names.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from pymongo import ASCENDING, GEOSPHERE, MongoClient
from pymongo.database import Database
from pymongo.errors import OperationFailure
from passlib.context import CryptContext

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

COLLECTIONS = (
    "devices",
    "events",
    "device_telemetry",
    "rules",
    "alerts",
    "incidents",
    "risk_scores",
    "users",
    "system_state",
    "ground_truth",
)

NUMBER_TYPES = ["double", "int", "long", "decimal"]


def _object_schema(required: list[str], properties: dict[str, Any]) -> dict[str, Any]:
    """Return a closed embedded-document schema."""
    return {
        "bsonType": "object",
        "required": required,
        "additionalProperties": False,
        "properties": properties,
    }


PAYLOAD_SCHEMAS = [
    _object_schema(
        ["user", "attempts"],
        {"user": {"bsonType": "string"}, "attempts": {"bsonType": "int", "minimum": 0}},
    ),
    _object_schema(
        ["topic", "clientId", "action"],
        {
            "topic": {"bsonType": "string"},
            "clientId": {"bsonType": "string"},
            "action": {"bsonType": "string"},
        },
    ),
    _object_schema(
        ["method", "path", "username", "status"],
        {
            "method": {"bsonType": "string"},
            "path": {"bsonType": "string"},
            "username": {"bsonType": "string"},
            "status": {"bsonType": "int"},
        },
    ),
    _object_schema(
        ["uri", "code"],
        {"uri": {"bsonType": "string"}, "code": {"bsonType": ["string", "int"]}},
    ),
    _object_schema(
        ["bytesOut", "bytesIn"],
        {
            "bytesOut": {"bsonType": ["int", "long"], "minimum": 0},
            "bytesIn": {"bsonType": ["int", "long"], "minimum": 0},
        },
    ),
]

EVENTS_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "ts",
            "deviceId",
            "protocol",
            "eventType",
            "srcIp",
            "geo",
            "payload",
            "prevHash",
            "hash",
        ],
        "properties": {
            "ts": {"bsonType": "date"},
            "deviceId": {"bsonType": "string"},
            "protocol": {"enum": ["mqtt", "coap", "http", "ssh", "telnet"]},
            "eventType": {"bsonType": "string"},
            "srcIp": {"bsonType": "string"},
            "geo": _object_schema(
                ["type", "coordinates"],
                {
                    "type": {"enum": ["Point"]},
                    "coordinates": {
                        "bsonType": "array",
                        "minItems": 2,
                        "maxItems": 2,
                        "items": {"bsonType": NUMBER_TYPES},
                    },
                },
            ),
            "payload": {"oneOf": PAYLOAD_SCHEMAS},
            "prevHash": {"bsonType": "string"},
            "hash": {"bsonType": "string"},
            "eventInsertedAt": {"bsonType": "date"},
            "chainSeq": {"bsonType": ["int", "long"], "minimum": 1},
            "ingestBatchId": {"bsonType": "string"},
        },
    }
}

RULES_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["ruleId", "name", "stage", "severity", "type", "window", "pipeline", "active"],
        "properties": {
            "ruleId": {"bsonType": "string"},
            "name": {"bsonType": "string"},
            "stage": {"bsonType": "string"},
            "severity": {"bsonType": "int", "minimum": 1, "maximum": 10},
            "type": {"bsonType": "string"},
            "window": {"bsonType": "object"},
            "pipeline": {"bsonType": "array", "items": {"bsonType": "object"}},
            "active": {"bsonType": "bool"},
        },
    }
}

ALERTS_VALIDATOR = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": [
            "ts",
            "ruleId",
            "deviceId",
            "actor",
            "targetIp",
            "stage",
            "severity",
            "eventIds",
            "eventInsertedAt",
            "alertCreatedAt",
        ],
        "properties": {
            "ts": {"bsonType": "date"},
            "ruleId": {"bsonType": "string"},
            "deviceId": {"bsonType": "string"},
            "actor": {"bsonType": "string"},
            "targetIp": {"bsonType": "string"},
            "stage": {"bsonType": "string"},
            "severity": {"bsonType": "int", "minimum": 1, "maximum": 10},
            "eventIds": {"bsonType": "array", "items": {"bsonType": "objectId"}},
            "incidentId": {"bsonType": "objectId"},
            "eventInsertedAt": {"bsonType": "date"},
            "alertCreatedAt": {"bsonType": "date"},
            "detectionLatencyMs": {"bsonType": NUMBER_TYPES, "minimum": 0},
            "dedupeKey": {"bsonType": "string"},
        },
    }
}


def _ensure_collection(db: Database[Any], name: str, **options: Any) -> None:
    if name not in db.list_collection_names():
        db.create_collection(name, **options)


def _apply_validator(db: Database[Any], name: str, validator: dict[str, Any]) -> None:
    db.command(
        "collMod",
        name,
        validator=validator,
        validationLevel="strict",
        validationAction="error",
    )


def ensure_collections(db: Database[Any], telemetry_ttl: int) -> None:
    """Create regular and time-series collections, then enforce validators."""
    for name in COLLECTIONS:
        if name == "device_telemetry":
            _ensure_collection(
                db,
                name,
                timeseries={"timeField": "ts", "metaField": "deviceId", "granularity": "minutes"},
                expireAfterSeconds=telemetry_ttl,
            )
        else:
            _ensure_collection(db, name)

    # Keep time-series retention synchronized when the environment changes.
    db.command("collMod", "device_telemetry", expireAfterSeconds=telemetry_ttl)
    _apply_validator(db, "events", EVENTS_VALIDATOR)
    _apply_validator(db, "rules", RULES_VALIDATOR)
    _apply_validator(db, "alerts", ALERTS_VALIDATOR)


def ensure_indexes(db: Database[Any], ttl_seconds: int) -> None:
    """Create stable named indexes and update the event TTL in place."""
    db.events.create_index([("deviceId", ASCENDING), ("ts", ASCENDING)], name="events_device_ts")
    db.events.create_index([("srcIp", ASCENDING), ("ts", ASCENDING)], name="events_src_ip_ts")
    db.events.create_index([("eventType", ASCENDING), ("ts", ASCENDING)], name="events_type_ts")
    db.events.create_index(
        [("deviceId", ASCENDING), ("chainSeq", ASCENDING)],
        name="events_device_chain_seq_unique",
        unique=True,
        partialFilterExpression={"chainSeq": {"$exists": True}},
    )
    ttl_name = "events_ts_ttl"
    if ttl_name not in db.events.index_information():
        db.events.create_index("ts", name=ttl_name, expireAfterSeconds=ttl_seconds)
    else:
        db.command("collMod", "events", index={"name": ttl_name, "expireAfterSeconds": ttl_seconds})

    db.alerts.create_index([("actor", ASCENDING), ("ts", ASCENDING)], name="alerts_actor_ts")
    db.alerts.create_index([("targetIp", ASCENDING), ("ts", ASCENDING)], name="alerts_target_ts")
    db.alerts.create_index("targetIp", name="alerts_target_ip")
    db.alerts.create_index("incidentId", name="alerts_incident")
    db.alerts.create_index(
        "dedupeKey", name="alerts_dedupe_unique", unique=True,
        partialFilterExpression={"dedupeKey": {"$exists": True}},
    )
    db.devices.create_index([("location", GEOSPHERE)], name="devices_location_2dsphere")
    db.devices.create_index("deviceId", name="devices_device_id_unique", unique=True)
    db.devices.create_index("ip", name="devices_ip_unique", unique=True)
    db.rules.create_index([("active", ASCENDING), ("stage", ASCENDING)], name="rules_active_stage")
    db.rules.create_index("ruleId", name="rules_rule_id_unique", unique=True)
    db.users.create_index("username", name="users_username_unique", unique=True)
    db.incidents.create_index(
        "chainKey", name="incidents_chain_key_unique", unique=True,
        partialFilterExpression={"chainKey": {"$exists": True}},
    )
    db.risk_scores.create_index(
        "deviceId", name="risk_device_id_unique", unique=True,
        partialFilterExpression={"deviceId": {"$exists": True}},
    )


def _privilege(db_name: str, collection: str, actions: list[str]) -> dict[str, Any]:
    return {"resource": {"db": db_name, "collection": collection}, "actions": actions}


def role_definitions(db_name: str) -> dict[str, list[dict[str, Any]]]:
    """Return least-privilege grants for each HoneyGraph database principal."""
    readable = list(COLLECTIONS)
    return {
        # find is necessary to obtain the previous per-device hash-chain head.
        "ingest_svc": [_privilege(db_name, "events", ["find", "insert"])],
        "detect_svc": [
            _privilege(db_name, "", ["changeStream"]),
            *[_privilege(db_name, name, ["find"]) for name in ("events", "rules", "devices", "device_telemetry")],
            *[
                _privilege(db_name, name, ["find", "insert", "update", "remove"])
                for name in ("alerts", "incidents", "risk_scores", "system_state")
            ],
            # Time-series rollups are deliberately written outside incident transactions.
            _privilege(db_name, "device_telemetry", ["insert"]),
        ],
        "analyst": [_privilege(db_name, name, ["find"]) for name in readable],
        "rule_admin": [_privilege(db_name, "rules", ["find", "insert", "update", "remove"])],
        "tamper_demo": [_privilege(db_name, "events", ["update", "remove"])],
        # Rule writes deliberately use the separate rule_admin principal/path.
        "api_svc": [
            _privilege(db_name, "", ["changeStream"]),
            *[
                _privilege(db_name, name, ["find"])
                for name in ("devices", "events", "device_telemetry", "rules", "alerts", "incidents", "risk_scores")
            ],
            _privilege(db_name, "incidents", ["update"]),
            _privilege(db_name, "users", ["find", "insert", "update"]),
            _privilege(db_name, "system_state", ["find", "insert", "update"]),
        ],
    }


def _upsert_role(db: Database[Any], role: str, privileges: list[dict[str, Any]]) -> None:
    try:
        db.command("createRole", role, privileges=privileges, roles=[])
    except OperationFailure as exc:
        if exc.code != 51002:  # RoleAlreadyExists
            raise
        db.command("updateRole", role, privileges=privileges, roles=[])


def ensure_rbac(db: Database[Any]) -> None:
    """Create/update custom roles and their password-authenticated users."""
    for role, privileges in role_definitions(db.name).items():
        _upsert_role(db, role, privileges)

    credentials = {
        "ingest_svc": os.environ["MONGO_INGEST_PASSWORD"],
        "detect_svc": os.environ["MONGO_DETECTOR_PASSWORD"],
        "analyst": os.environ["MONGO_ANALYST_PASSWORD"],
        "rule_admin": os.environ["MONGO_RULE_ADMIN_PASSWORD"],
        "tamper_demo": os.environ["MONGO_TAMPER_PASSWORD"],
        "api_svc": os.environ["MONGO_API_PASSWORD"],
    }
    existing = {user["user"] for user in db.command("usersInfo")["users"]}
    for username, password in credentials.items():
        role = {"role": username, "db": db.name}
        if username in existing:
            db.command("updateUser", username, pwd=password, roles=[role])
        else:
            db.command("createUser", username, pwd=password, roles=[role])


def ensure_application_users(db: Database[Any]) -> None:
    """Idempotently seed one application analyst and administrator."""
    context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    seeds = (
        (os.getenv("APP_ANALYST_USERNAME", "analyst"), os.environ["APP_ANALYST_PASSWORD"], "analyst"),
        (os.getenv("APP_ADMIN_USERNAME", "admin"), os.environ["APP_ADMIN_PASSWORD"], "admin"),
    )
    for username, password, role in seeds:
        existing = db.users.find_one({"username": username})
        if existing and context.verify(password, existing["passwordHash"]):
            continue
        db.users.update_one(
            {"username": username},
            {"$set": {"passwordHash": context.hash(password), "role": role, "active": True}}, upsert=True,
        )


def initialize() -> None:
    uri = os.environ["MONGODB_URI"]
    db_name = os.getenv("MONGO_DATABASE", "honeygraph")
    # Development defaults to 7 days; CERT-In production deployments should use 180 days.
    ttl_days = int(os.getenv("EVENT_TTL_DAYS", "7"))
    if ttl_days <= 0:
        raise ValueError("EVENT_TTL_DAYS must be positive")
    ttl_seconds = ttl_days * 24 * 60 * 60

    with MongoClient(uri, serverSelectionTimeoutMS=10_000) as client:
        client.admin.command("ping")
        db = client[db_name]
        ensure_collections(db, ttl_seconds)
        ensure_indexes(db, ttl_seconds)
        ensure_rbac(db)
        ensure_application_users(db)
        print(f"HoneyGraph database initialized: {db_name} (event TTL: {ttl_days} days)")


if __name__ == "__main__":
    initialize()

