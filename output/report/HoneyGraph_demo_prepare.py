"""Fresh-time rehearsal traffic for the HoneyGraph presentation guide.

Run from the repository root. Uses the real ingestion API, running detector,
and existing MongoDB chain/risk aggregations; does not modify application code.
Administrative .env access is for local demo preparation only. No secrets print.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
from dotenv import load_dotenv
from pymongo import MongoClient
from simulator.run import generate
from simulator.sinks import ApiSink
from workers.chain_builder import ChainBuilder


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=["mirai_bruteforce", "recon", "credential_stuffing", "mqtt_abuse", "lateral_movement", "exfil_burst"])
    parser.add_argument("--seed", type=int, default=501)
    parser.add_argument("--materialize", action="store_true", help="Also materialize a non-lateral incident and its risk in the existing transaction")
    args = parser.parse_args()
    load_dotenv(ROOT / ".env")
    inventory, events, labels, counts = generate(500, 0, 0, [args.scenario], args.seed)
    now = datetime.now(timezone.utc)
    shift = now - timedelta(seconds=1) - max(e["ts"] for e in events)
    with MongoClient(os.environ["MONGODB_URI"], tz_aware=True, serverSelectionTimeoutMS=10000) as client:
        db = client[os.getenv("MONGO_DATABASE", "honeygraph")]
        client.admin.command("ping")
        # Preserve existing inventory/IP assignments, insert only missing assets.
        stored = {d["deviceId"]: d for d in db.devices.find({})}
        generated_ip_to_id = {d["ip"]: d["deviceId"] for d in inventory}
        for device in inventory:
            if device["deviceId"] not in stored:
                db.devices.insert_one(device.copy())
                stored[device["deviceId"]] = device
        for event in events:
            event["ts"] += shift
            source_id = generated_ip_to_id.get(event["srcIp"])
            if source_id in stored:
                event["srcIp"] = stored[source_id]["ip"]
            event["geo"] = stored[event["deviceId"]]["location"]
        events.sort(key=lambda e: (e["ts"], e["deviceId"]))
        for device_id in {e["deviceId"] for e in events}:
            previous = db.events.find_one({"deviceId": device_id}, sort=[("ts", -1)])
            first_ts = min(e["ts"] for e in events if e["deviceId"] == device_id)
            if previous and previous["ts"] >= first_ts:
                raise RuntimeError("Traffic would be backdated for " + device_id + ". Wait a few seconds or choose a different seed.")
        for item in labels:
            item["scenarioId"] += "-rehearsal-" + now.strftime("%Y%m%dT%H%M%S%f")
            for bound in ("start", "end"):
                item["eventTimeRange"][bound] += shift
            source_id = generated_ip_to_id.get(item["actor"])
            if source_id in stored:
                item["actor"] = stored[source_id]["ip"]
        if labels:
            db.ground_truth.insert_many(labels)
        if args.scenario == "exfil_burst":
            device = events[0]["deviceId"]
            baseline = events[0]["payload"]["bytesOut"] // 20
            db.device_telemetry.insert_many([
                {"ts": now - timedelta(minutes=i + 1), "deviceId": device,
                 "eventCount": 1, "failedLogins": 0, "bytesOut": baseline}
                for i in range(3)
            ])
        sink = ApiSink(f"http://localhost:{os.getenv('BACKEND_PORT', '8000')}")
        started = time.monotonic()
        try:
            identifiers = sink.write(events)
        finally:
            sink.close()
        target_devices = sorted({e["deviceId"] for e in events})
        query = {"deviceId": {"$in": target_devices}, "ts": {"$gte": min(e["ts"] for e in events), "$lte": max(e["ts"] for e in events)}}
        alerts = []
        deadline = time.monotonic() + 20
        expected_rule = {"mirai_bruteforce": "R-BRUTE-01", "recon": "R-RECON-03",
                         "credential_stuffing": "R-STUFF-04", "mqtt_abuse": "R-MQTT-05",
                         "lateral_movement": "R-LATERAL-06", "exfil_burst": "R-EXFIL-07"}[args.scenario]
        while time.monotonic() < deadline:
            alerts = list(db.alerts.find(query).sort("ts", 1))
            lateral = [a for a in alerts if a["ruleId"] == "R-LATERAL-06"]
            expected_present = any(a["ruleId"] == expected_rule for a in alerts)
            if expected_present and time.monotonic() - started >= 1 and (args.scenario != "lateral_movement" or len(lateral) >= len(events)):
                break
            time.sleep(0.1)
        if not any(a["ruleId"] == expected_rule for a in alerts):
            raise RuntimeError("Ingest succeeded but expected rule " + expected_rule + " did not alert in 20 s. Inspect detector logs/rule activation.")
        incident = None
        if args.scenario == "lateral_movement" or args.materialize:
            seed_alert = lateral[-1] if args.scenario == "lateral_movement" else alerts[-1]
            if args.scenario == "lateral_movement" and len(lateral) < len(events):
                raise RuntimeError("Not every lateral hop was detected; inspect alert/rule cooldown state.")
            incident_id = ChainBuilder(client, db.name).build(seed_alert["_id"])
            row = db.incidents.find_one({"_id": incident_id})
            if args.scenario == "lateral_movement":
                injected = [(e["srcIp"], stored[e["deviceId"]]["ip"]) for e in events]
                recovered = [(a["actor"], a["targetIp"]) for a in row["chain"]]
                if injected != recovered:
                    raise RuntimeError("Recovered chain differs from injected hops; use another seed for an isolated rehearsal.")
            incident = {"id": str(incident_id), "status": row["status"], "hops": [{"hop": a["hop"], "actor": a["actor"], "targetIp": a["targetIp"]} for a in row["chain"]]}
        summary = {"recordedAt": now.isoformat(), "scenario": args.scenario, "seed": args.seed,
                   "eventsInserted": len(identifiers), "devices": target_devices,
                   "elapsedSeconds": round(time.monotonic() - started, 3),
                   "alerts": [{"id": str(a["_id"]), "ruleId": a["ruleId"], "deviceId": a["deviceId"],
                               "stage": a["stage"], "severity": a["severity"],
                               "latencyMs": round((a["alertCreatedAt"] - a["eventInsertedAt"]).total_seconds() * 1000, 2)} for a in alerts],
                   "incident": incident,
                   "riskScores": [{"deviceId": r["deviceId"], "score": round(r["score"], 3)} for r in db.risk_scores.find({"deviceId": {"$in": target_devices}})]}
        destination = ROOT / "output" / "report" / f"rehearsal_{args.scenario}.json"
        destination.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
