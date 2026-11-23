"""Idempotently seed MongoDB-native HoneyGraph detection rules."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from pymongo import MongoClient, ReplaceOne

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

import sys

sys.path.insert(0, str(ROOT / "backend"))
from app.rule_validator import validate_rule  # noqa: E402


def rules() -> list[dict]:
    return [
        {
            "ruleId": "R-BRUTE-01", "name": "Repeated device login failures", "stage": "credential-access",
            "severity": 7, "type": "windowed", "window": {"seconds": 300}, "trigger": {"eventType": "login_failed"},
            "pipeline": [
                {"$match": {"srcIp": "{{srcIp}}", "deviceId": "{{deviceId}}", "eventType": "login_failed"}},
                {"$group": {"_id": {"actor": "$srcIp", "device": "$deviceId"}, "count": {"$sum": 1}, "eventIds": {"$push": "$_id"}}},
                {"$match": {"count": {"$gte": 5}}}, {"$limit": 1},
            ], "cooldownSeconds": 300, "active": True,
        },
        {
            "ruleId": "R-BRUTE-SUCCESS-02", "name": "Failures followed by success", "stage": "initial-access",
            "severity": 9, "type": "sequence", "window": {"seconds": 300}, "trigger": {"eventType": "login_success"},
            "pipeline": [
                {"$match": {"srcIp": "{{srcIp}}", "deviceId": "{{deviceId}}", "eventType": {"$in": ["login_failed", "login_success"]}}},
                {"$group": {"_id": "$srcIp", "failures": {"$sum": {"$cond": [{"$eq": ["$eventType", "login_failed"]}, 1, 0]}}, "successes": {"$sum": {"$cond": [{"$eq": ["$eventType", "login_success"]}, 1, 0]}}, "eventIds": {"$push": "$_id"}}},
                {"$match": {"failures": {"$gte": 5}, "successes": {"$gte": 1}}}, {"$limit": 1},
            ], "cooldownSeconds": 300, "active": True,
        },
        {
            "ruleId": "R-RECON-03", "name": "One source scans many devices", "stage": "discovery",
            "severity": 6, "type": "distinct", "window": {"seconds": 300}, "trigger": {"eventType": "port_scan"},
            "pipeline": [
                {"$match": {"srcIp": "{{srcIp}}", "eventType": "port_scan"}},
                {"$group": {"_id": "$srcIp", "targets": {"$addToSet": "$deviceId"}, "eventIds": {"$push": "$_id"}}},
                {"$project": {"eventIds": 1, "distinctCount": {"$size": "$targets"}}},
                {"$match": {"distinctCount": {"$gte": 20}}}, {"$limit": 1},
            ], "cooldownSeconds": 300, "active": True,
        },
        {
            "ruleId": "R-STUFF-04", "name": "HTTP credential stuffing", "stage": "credential-access",
            "severity": 7, "type": "distinct", "window": {"seconds": 300}, "trigger": {"eventType": "login_failed"},
            "pipeline": [
                {"$match": {"srcIp": "{{srcIp}}", "protocol": "http", "eventType": "login_failed"}},
                {"$group": {"_id": "$srcIp", "usernames": {"$addToSet": "$payload.username"}, "eventIds": {"$push": "$_id"}}},
                {"$project": {"eventIds": 1, "distinctCount": {"$size": "$usernames"}}},
                {"$match": {"distinctCount": {"$gte": 10}}}, {"$limit": 1},
            ], "cooldownSeconds": 300, "active": True,
        },
        {
            "ruleId": "R-MQTT-05", "name": "Unauthorized restricted MQTT publish", "stage": "impact",
            "severity": 9, "type": "allowlist", "window": {"seconds": 60}, "trigger": {"eventType": "restricted_publish"},
            "pipeline": [{"$match": {"_id": "{{eventId}}", "eventType": "restricted_publish", "payload.clientId": {"$not": {"$in": ["signal-controller-allowlisted"]}}}}, {"$limit": 1}],
            "cooldownSeconds": 60, "active": True,
        },
        {
            "ruleId": "R-LATERAL-06", "name": "Internal device lateral login", "stage": "lateral-movement",
            "severity": 8, "type": "sequence", "window": {"seconds": 600}, "trigger": {"eventType": "lateral_login"},
            "pipeline": [{"$match": {"_id": "{{eventId}}", "srcIp": "{{srcIp}}", "eventType": "lateral_login"}}, {"$limit": 1}],
            "cooldownSeconds": 300, "active": True,
        },
        {
            "ruleId": "R-EXFIL-07", "name": "Outbound bytes exceed telemetry baseline", "stage": "exfiltration",
            "severity": 9, "type": "baseline", "window": {"seconds": 600}, "trigger": {"eventType": "exfil_burst"},
            "pipeline": [{"$match": {"deviceId": "{{deviceId}}", "eventType": "exfil_burst"}}, {"$limit": 1}],
            "baselineMultiplier": 5, "cooldownSeconds": 300, "active": True,
        },
        {
            "ruleId": "R-SCAN-PORTS-08", "name": "Rapid multi-port scan", "stage": "reconnaissance",
            "severity": 5, "type": "windowed", "window": {"seconds": 120}, "trigger": {"eventType": "port_scan"},
            "pipeline": [{"$match": {"srcIp": "{{srcIp}}", "eventType": "port_scan"}}, {"$group": {"_id": "$srcIp", "count": {"$sum": 1}, "eventIds": {"$push": "$_id"}}}, {"$match": {"count": {"$gte": 10}}}, {"$limit": 1}],
            "cooldownSeconds": 120, "active": True,
        },
        {
            "ruleId": "R-OFFHOURS-ADMIN-09", "name": "Administrative command execution", "stage": "execution",
            "severity": 8, "type": "windowed", "window": {"seconds": 300}, "trigger": {"eventType": "command_exec"},
            "pipeline": [{"$match": {"srcIp": "{{srcIp}}", "deviceId": "{{deviceId}}", "eventType": "command_exec", "payload.user": "admin"}}, {"$limit": 1}],
            "cooldownSeconds": 300, "active": True,
        },
        {
            "ruleId": "R-NEWUSER-CMD-10", "name": "New login followed by command", "stage": "execution",
            "severity": 8, "type": "sequence", "window": {"seconds": 300}, "trigger": {"eventType": "command_exec"},
            "pipeline": [{"$match": {"srcIp": "{{srcIp}}", "deviceId": "{{deviceId}}", "eventType": {"$in": ["login_success", "command_exec"]}}}, {"$group": {"_id": "$srcIp", "types": {"$addToSet": "$eventType"}, "eventIds": {"$push": "$_id"}}}, {"$match": {"types": {"$all": ["login_success", "command_exec"]}}}, {"$limit": 1}],
            "cooldownSeconds": 300, "active": True,
        },
    ]


def rule_admin_uri() -> str:
    database = os.getenv("MONGO_DATABASE", "honeygraph")
    return (
        f"mongodb://rule_admin:{quote_plus(os.environ['MONGO_RULE_ADMIN_PASSWORD'])}@localhost:{os.getenv('MONGO1_PORT', '27017')}/{database}"
        f"?authSource={database}&replicaSet=rs0&directConnection=true"
    )


def main() -> None:
    documents = [validate_rule(rule) for rule in rules()]
    with MongoClient(rule_admin_uri()) as client:
        collection = client[os.getenv("MONGO_DATABASE", "honeygraph")].rules
        result = collection.bulk_write(
            [ReplaceOne({"ruleId": rule["ruleId"]}, rule, upsert=True) for rule in documents], ordered=False
        )
    print(f"Seeded {len(documents)} rules (upserted={result.upserted_count}, modified={result.modified_count})")


if __name__ == "__main__":
    main()
