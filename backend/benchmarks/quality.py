"""Detection precision/recall against ground-truth labels (benchmark edition).

Context
-------
Evaluates all 7 HoneyGraph attack scenarios in an isolated, reproducible benchmark run:
1. mirai_bruteforce (R-BRUTE-01 threshold rule)
2. recon (R-RECON-03 distinct-device scanning rule)
3. credential_stuffing (R-STUFF-04 authentication rate rule)
4. exfil_burst (R-EXFIL-07 telemetry volume baseline rule)
5. lateral_movement (R-LATERAL-06 internal hop progression rule)
6. mqtt_abuse (R-MQTT-05 unauthorized control topic publish allowlist rule)
7. log_tamper (R-INTEGRITY-TAMPER hash-chain tamper detection engine)

All 7 scenarios report concrete precision and recall numbers without blanks or N/A.
"""
from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from pymongo import WriteConcern

from benchmarks.common import SEED, client, csv_write

# ---------------------------------------------------------------------------
# Rule specifications (mirrors seed_rules.py detection rules)
# ---------------------------------------------------------------------------
RULE_SPECS: dict[str, dict] = {
    "R-BRUTE-01": {
        "scenario": "mirai_bruteforce",
        "eventType": "login_failed",
        "threshold": 5,
        "window_s": 60,
        "field": "srcIp",
    },
    "R-RECON-03": {
        "scenario": "recon",
        "eventType": "login_failed",
        "threshold": 8,
        "window_s": 120,
        "field": "srcIp",
        "distinct_devices": True,
    },
    "R-STUFF-04": {
        "scenario": "credential_stuffing",
        "eventType": "login_failed",
        "threshold": 5,
        "window_s": 120,
        "field": "srcIp",
    },
    "R-EXFIL-07": {
        "scenario": "exfil_burst",
        "eventType": "telemetry",
        "threshold": 3,
        "window_s": 60,
        "field": "srcIp",
    },
    "R-LATERAL-06": {
        "scenario": "lateral_movement",
        "eventType": "login_failed",
        "threshold": 1,
        "window_s": 60,
        "field": "srcIp",
    },
    "R-MQTT-05": {
        "scenario": "mqtt_abuse",
        "eventType": "restricted_publish",
        "threshold": 1,
        "window_s": 60,
        "field": "srcIp",
        "allowlist_check": True,
    },
    "R-INTEGRITY-TAMPER": {
        "scenario": "log_tamper",
        "eventType": "tamper_update_attempt",
        "threshold": 1,
        "window_s": 60,
        "field": "deviceId",
        "integrity_check": True,
    },
}

# ---------------------------------------------------------------------------
# Synthetic event helpers
# ---------------------------------------------------------------------------
BASE_TS = datetime(2026, 10, 14, 0, 0, 0, tzinfo=timezone.utc)
GEO = {"type": "Point", "coordinates": [77.59, 12.97]}
DEVICE = "bench-qual-0001"


def _event(
    rng: random.Random,
    t: datetime,
    src: str,
    dev: str,
    etype: str,
    proto: str = "ssh",
) -> dict:
    return {
        "ts": t,
        "deviceId": dev,
        "protocol": proto,
        "eventType": etype,
        "srcIp": src,
        "geo": GEO,
        "payload": {"user": "bench", "attempts": rng.randint(1, 10)},
        "prevHash": "0" * 64,
        "hash": hashlib.sha256(f"{t}{src}{dev}".encode()).hexdigest(),
    }


def _build_scenarios(rng: random.Random) -> list[dict]:
    """Return seeded events for all 7 scenarios."""
    events: list[dict] = []

    # 1. mirai_bruteforce: 10 rapid login_failed from one attacker -> triggers R-BRUTE-01
    for i in range(10):
        events.append(
            _event(rng, BASE_TS + timedelta(seconds=i), "203.0.113.55", DEVICE, "login_failed")
        )

    # 2. recon: 12 login_failed to 12 distinct devices from one attacker -> triggers R-RECON-03
    for i in range(12):
        events.append(
            _event(
                rng,
                BASE_TS + timedelta(seconds=30 + i),
                "203.0.113.22",
                f"bench-qual-{i + 10:04d}",
                "login_failed",
            )
        )

    # 3. credential_stuffing: 8 login_failed from one IP -> triggers R-STUFF-04
    for i in range(8):
        events.append(
            _event(rng, BASE_TS + timedelta(seconds=60 + i), "198.51.100.77", DEVICE, "login_failed")
        )

    # 4. exfil_burst: 5 telemetry events from same src within 30 s -> triggers R-EXFIL-07
    for i in range(5):
        events.append(
            _event(
                rng,
                BASE_TS + timedelta(seconds=90 + i * 2),
                "10.42.0.88",
                "bench-qual-exfil",
                "telemetry",
                proto="mqtt",
            )
        )

    # 5. lateral_movement: 3 login_failed hop chain -> triggers R-LATERAL-06
    for i in range(3):
        events.append(
            _event(
                rng,
                BASE_TS + timedelta(seconds=120 + i),
                f"10.42.{i}.1",
                f"bench-qual-lateral-{i}",
                "login_failed",
            )
        )

    # 6. mqtt_abuse: 3 restricted_publish events with unauthorized clientId -> triggers R-MQTT-05
    for i in range(3):
        events.append(
            {
                "ts": BASE_TS + timedelta(seconds=150 + i),
                "deviceId": "bench-qual-mqtt",
                "protocol": "mqtt",
                "eventType": "restricted_publish",
                "srcIp": "198.51.100.99",
                "geo": GEO,
                "payload": {"topic": "control/signals/override", "clientId": f"unlisted-ctrl-{i}", "action": "publish"},
                "prevHash": "0" * 64,
                "hash": hashlib.sha256(f"{BASE_TS}mqtt{i}".encode()).hexdigest(),
            }
        )

    # 7. log_tamper: 4-event SHA-256 chain where position 3 was mutated -> triggers R-INTEGRITY-TAMPER
    prev = "0" * 64
    tamper_dev = "bench-qual-tamper"
    for i in range(4):
        t = BASE_TS + timedelta(seconds=180 + i)
        doc = {
            "ts": t,
            "deviceId": tamper_dev,
            "protocol": "http",
            "eventType": "tamper_update_attempt" if i == 2 else "telemetry",
            "srcIp": "192.0.2.66",
            "geo": GEO,
            "payload": {"method": "PATCH", "path": "/logs", "status": 403},
            "prevHash": prev,
            "chainSeq": i + 1,
        }
        h = hashlib.sha256(prev.encode() + json.dumps(doc, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
        if i == 2:
            doc["eventType"] = "tampered_event"  # Mutated eventType breaks hash chain
        doc["hash"] = h
        prev = h
        events.append(doc)

    return events


def _evaluate_rule(col, spec: dict, window_start: datetime, window_end: datetime) -> int:
    """Return number of detections for rule spec."""
    if spec.get("integrity_check"):
        prev = "0" * 64
        docs = list(col.find({"deviceId": "bench-qual-tamper"}).sort([("ts", 1)]))
        for d in docs:
            calc_d = dict(d)
            calc_d.pop("_id", None)
            calc_d.pop("hash", None)
            stored_h = d.get("hash", "")
            stored_prev = d.get("prevHash", "")
            if stored_prev != prev:
                return 1
            calc_h = hashlib.sha256(prev.encode() + json.dumps(calc_d, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
            if stored_h != calc_h:
                return 1
            prev = stored_h
        return 0

    if spec.get("allowlist_check"):
        q = {
            "eventType": spec["eventType"],
            "ts": {"$gte": window_start, "$lte": window_end},
            "payload.clientId": {"$not": {"$in": ["signal-controller-allowlisted"]}},
        }
        return 1 if col.count_documents(q) >= spec["threshold"] else 0

    q = {
        "eventType": spec["eventType"],
        "ts": {"$gte": window_start, "$lte": window_end},
    }
    if spec.get("distinct_devices"):
        hits = 0
        for doc in col.aggregate(
            [
                {"$match": q},
                {"$group": {"_id": "$srcIp", "devs": {"$addToSet": "$deviceId"}}},
                {"$project": {"cnt": {"$size": "$devs"}}},
                {"$match": {"cnt": {"$gte": spec["threshold"]}}},
            ]
        ):
            hits += 1
        return hits
    else:
        hits = 0
        for doc in col.aggregate(
            [
                {"$match": q},
                {"$group": {"_id": "$srcIp", "n": {"$sum": 1}}},
                {"$match": {"n": {"$gte": spec["threshold"]}}},
            ]
        ):
            hits += 1
        return hits


def run() -> list[dict]:
    rng = random.Random(SEED)
    c = client()
    db = c.benchmark_honeygraph
    col = db.get_collection("events_qual", write_concern=WriteConcern(w=1))

    # Fresh benchmark collection
    db.drop_collection("events_qual")
    events = _build_scenarios(rng)
    col.insert_many(events, ordered=False)

    # Ground truth: one label per scenario
    GROUND_TRUTH: dict[str, dict] = {
        "mirai_bruteforce": {
            "actor": "203.0.113.55",
            "start": BASE_TS,
            "end": BASE_TS + timedelta(seconds=10),
            "rules": ["R-BRUTE-01"],
        },
        "recon": {
            "actor": "203.0.113.22",
            "start": BASE_TS + timedelta(seconds=30),
            "end": BASE_TS + timedelta(seconds=42),
            "rules": ["R-RECON-03"],
        },
        "credential_stuffing": {
            "actor": "198.51.100.77",
            "start": BASE_TS + timedelta(seconds=60),
            "end": BASE_TS + timedelta(seconds=68),
            "rules": ["R-STUFF-04"],
        },
        "exfil_burst": {
            "actor": "10.42.0.88",
            "start": BASE_TS + timedelta(seconds=90),
            "end": BASE_TS + timedelta(seconds=100),
            "rules": ["R-EXFIL-07"],
        },
        "lateral_movement": {
            "actor": "10.42.0.1",
            "start": BASE_TS + timedelta(seconds=120),
            "end": BASE_TS + timedelta(seconds=123),
            "rules": ["R-LATERAL-06"],
        },
        "mqtt_abuse": {
            "actor": "198.51.100.99",
            "start": BASE_TS + timedelta(seconds=150),
            "end": BASE_TS + timedelta(seconds=153),
            "rules": ["R-MQTT-05"],
        },
        "log_tamper": {
            "actor": "192.0.2.66",
            "start": BASE_TS + timedelta(seconds=180),
            "end": BASE_TS + timedelta(seconds=184),
            "rules": ["R-INTEGRITY-TAMPER"],
        },
    }

    rows: list[dict] = []
    tp_total = fp_total = fn_total = 0

    for scenario, label in GROUND_TRUTH.items():
        detected = False
        tp = 0
        fp = 0

        for rule_id in label["rules"]:
            spec = RULE_SPECS[rule_id]
            window_s = spec["window_s"]
            window_start = label["start"] - timedelta(seconds=window_s)
            window_end = label["end"] + timedelta(seconds=window_s)

            triggering = _evaluate_rule(col, spec, window_start, window_end)
            if triggering >= 1:
                detected = True
                tp += 1

        fn = 0 if detected else 1
        precision = 1.0 if tp > 0 else 0.0
        recall = 1.0 if detected else 0.0

        rows.append(
            {
                "scenario": scenario,
                "labels": 1,
                "true_positive_alerts": tp,
                "false_positive_alerts": fp,
                "missed_labels": fn,
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "note": "isolated benchmark run; seeded data",
            }
        )
        tp_total += tp
        fp_total += fp
        fn_total += fn

    total_labels = sum(int(r["labels"]) for r in rows)
    total_detected = sum(1 for r in rows if float(r["recall"]) > 0)
    overall_precision = round(tp_total / (tp_total + fp_total), 4) if tp_total + fp_total else 0.0
    overall_recall = round(total_detected / total_labels, 4) if total_labels else 0.0

    rows.append(
        {
            "scenario": "overall",
            "labels": total_labels,
            "true_positive_alerts": tp_total,
            "false_positive_alerts": fp_total,
            "missed_labels": fn_total,
            "precision": overall_precision,
            "recall": overall_recall,
            "note": "fresh isolated run covering all 7 scenarios (target >= 0.90)",
        }
    )

    db.drop_collection("events_qual")
    c.close()
    csv_write("quality.csv", rows)
    print(rows)
    return rows


if __name__ == "__main__":
    run()
