"""MongoDB connection helpers for backend service principals."""

from __future__ import annotations

import os
from urllib.parse import quote_plus

from pymongo import MongoClient


def ingest_uri() -> str:
    explicit = os.getenv("MONGO_INGEST_URI")
    if explicit:
        return explicit
    database = os.getenv("MONGO_DATABASE", "honeygraph")
    port = os.getenv("MONGO1_PORT", "27017")
    username = os.getenv("MONGO_INGEST_USERNAME", "ingest_svc")
    password = os.environ["MONGO_INGEST_PASSWORD"]
    return (
        f"mongodb://{quote_plus(username)}:{quote_plus(password)}@localhost:{port}/{database}"
        f"?authSource={database}&replicaSet=rs0&directConnection=true"
    )


def ingest_client() -> MongoClient:
    return MongoClient(ingest_uri(), serverSelectionTimeoutMS=10_000)


def service_uri(username: str, password: str) -> str:
    explicit = os.getenv(f"MONGO_{username.upper()}_URI")
    if explicit:
        return explicit
    database = os.getenv("MONGO_DATABASE", "honeygraph")
    port = os.getenv("MONGO1_PORT", "27017")
    return (
        f"mongodb://{quote_plus(username)}:{quote_plus(password)}@localhost:{port}/{database}"
        f"?authSource={database}&replicaSet=rs0&directConnection=true"
    )


def api_client() -> MongoClient:
    uri = os.getenv("MONGO_API_URI") or service_uri(os.getenv("MONGO_API_USERNAME", "api_svc"), os.environ["MONGO_API_PASSWORD"])
    return MongoClient(uri, serverSelectionTimeoutMS=10_000)

