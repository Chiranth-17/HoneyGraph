"""Index executionStats comparison on the million-event corpus."""
from __future__ import annotations

from datetime import timedelta
from benchmarks.common import client, csv_write


def stats(col, q):
    e = col.find(q).explain()
    s = e["executionStats"]
    return {
        "documents_examined": s["totalDocsExamined"],
        "keys_examined": s["totalKeysExamined"],
        "time_ms": s["executionTimeMillis"],
        "returned": s["nReturned"],
    }


def run():
    c = client()
    db = c.benchmark_honeygraph
    col = db.events_hash
    rows = []

    first = col.find_one(sort=[("ts", 1)])
    t0 = first["ts"] if first and "ts" in first else None
    t1 = t0 + timedelta(seconds=10) if t0 else None

    # Compound indexes (field, ts) query field and the indexed time window
    specs = [
        ("device_ts", [("deviceId", 1), ("ts", 1)], {"deviceId": "bench-0042"}),
        ("src_ts", [("srcIp", 1), ("ts", 1)], {"srcIp": "198.51.100.43"}),
        (
            "event_type_ts",
            [("eventType", 1), ("ts", 1)],
            {"eventType": "login_failed", "ts": {"$gte": t0, "$lte": t1}}
            if t0
            else {"eventType": "login_failed"},
        ),
    ]

    for name, spec, q in specs:
        for idx in list(col.list_indexes()):
            if idx["name"] != "_id_":
                col.drop_index(idx["name"])
        rows.append({"index": name, "state": "before", **stats(col, q)})
        col.create_index(spec, name=name)
        rows.append({"index": name, "state": "after", **stats(col, q)})

    # Alerts-equivalent corpus uses the same scale and access pattern.
    db.drop_collection("alerts_bench")
    a = db.alerts_bench
    a.insert_many(
        ({"actor": f"198.51.100.{1 + i % 250}", "ts": i} for i in range(100_000)),
        ordered=False,
    )
    q = {"actor": "198.51.100.43"}
    rows.append({"index": "alerts_actor_ts", "state": "before", **stats(a, q)})
    a.create_index([("actor", 1), ("ts", 1)], name="actor_ts")
    rows.append({"index": "alerts_actor_ts", "state": "after", **stats(a, q)})

    csv_write("indexes.csv", rows)
    print(rows)
    c.close()
    return rows


if __name__ == "__main__":
    run()
