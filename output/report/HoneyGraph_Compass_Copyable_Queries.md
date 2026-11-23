# HoneyGraph: MongoDB Compass Demo Guide

Prepared 19 November 2026. No passwords are included.

## Page 1: HoneyGraph in MongoDB Compass

A simple live demonstration guide for your DBMS presentation

Prepared 19 November 2026. Use this guide beside Compass and the HoneyGraph dashboard.

### Opening words

> SAY: Good morning. I will show the database behind HoneyGraph using MongoDB Compass. Our project uses simulated IoT traffic. MongoDB stores the devices and event evidence, evaluates detection rules, connects alerts into incidents and stores device risk.

> SAY: Compass lets us inspect the data and run queries directly. The dashboard displays the results produced by our application and database.

| Time | What to show | DBMS point |
| --- | --- | --- |
| 1 minute | Connect and expand honeygraph | Database, collections and documents |
| 2 minutes | devices and events | Document fields, filtering and projection |
| 2 minutes | rules, alerts and incidents | Stored rules and evidence relationships |
| 2 minutes | Aggregation and Explain | Grouping and query optimization |
| 1 minute | Validation and indexes | Constraints, uniqueness and retention |
| Optional | Locations, replica set and integrity | Spatial queries, replication and evidence |

### The order to remember

devices -> events -> rules -> alerts -> incidents -> risk_scores. Then demonstrate Aggregations, Indexes and Validation.

### How to use the boxes

SAY boxes contain sentences you can read during the presentation. Code boxes contain filters, pipelines or shell commands. Each page tells you exactly where to paste them.

> NOTE: The document is a guide, not a new benchmark report. Queries were checked against the running database without generating traffic or modifying records. Counts will change when you launch scenarios.

## Page 2: 1. Connect to the correct server

Complete this before the evaluator arrives

1. Open Docker Desktop. From the project folder, run mingw32-make up if the stack is stopped.
2. In Compass, edit localhost:37017 or create a connection with the URI below.
3. Open Advanced Connection Options. In General, choose mongodb and enable Direct Connection.
4. In Advanced, leave Replica Set Name empty. Your Compass version warned against combining that field with Direct Connection.
5. Enter the existing database credentials in Authentication, then click Save & Connect.

```
mongodb://localhost:37017/?directConnection=true&authSource=admin
```

| Authentication setting | Value |
| --- | --- |
| Method | Username / Password |
| Username | root |
| Password | Actual MONGO_ROOT_PASSWORD value from the project .env |
| Authentication Database | admin |
| Mechanism | Default |

Copy only the password value after the equals sign, without surrounding quotes. Compass does not automatically read the project .env. Keep passwords off your presentation screen.

### Why this connection matters

| Address | What it is |
| --- | --- |
| localhost:27017 | A separate Windows MongoDB server with an older three-collection database |
| localhost:37017 | HoneyGraph's authenticated Docker MongoDB member |

> SAY: The application database is named honeygraph. The three MongoDB containers are replica-set servers. They are different from the collections inside the database.

> NOTE: Direct connection changes how Compass connects. It does not remove the server's replica set. If the old rendering error returns, use View -> Reload, Ctrl+Shift+R, then reconnect.

## Page 3: 2. Prepare fresh demonstration data

Use the dashboard to generate records, then inspect them in Compass

1. Open http://localhost:5173 and sign in with your configured application admin account.
2. Open Scenarios & Users, select mirai_bruteforce and click Launch once. Wait until the job completes.
3. Launch lateral_movement once and wait for completion. Keep its Open incident link available.
4. Return to Compass. Expand localhost:37017, then honeygraph. Refresh the collection or click Find after switching back.
5. Confirm that events contains fresh records before you begin your presentation.

### What to expect

| Collection | Preparation check |
| --- | --- |
| devices | The project inventory contains about 500 virtual devices |
| events | Fresh scenario events have current timestamps |
| rules | Active seeded rules are available |
| alerts | Recent detections show event references |
| incidents | A completed lateral job links to its new incident |
| device_telemetry | May be empty until a rollup job runs |

> SAY: The dashboard sends simulated events through the ingestion service. It validates and hashes the events before storing them. We now inspect the resulting documents directly in Compass.

### If a collection looks empty

Clear the Filter field and click Find. Raw events expire after seven days in this setup, so old alerts can remain after their raw event documents have expired. Launch a fresh scenario to demonstrate evidence links.

Some development/test documents contain only fields such as marker. The filters later in this guide select full application records for presentation.

> NOTE: You do not need to reseed the database before every demo. Seeding may overwrite seeded rule edits. If a job reports no new alert, check its message, active rules and cooldown rather than repeatedly clicking Launch.

## Page 4: 3. Devices and raw events

Show documents, selection, projection and ordering

### A. Device inventory

1. Open devices -> Documents. Expand one record and show deviceId, ip, type, firmware, protocol and location.
2. Open the query-bar Options if needed. Paste the following object into Project, then click Find.

```
{
  "_id": 0,
  "deviceId": 1,
  "ip": 1,
  "type": 1,
  "protocol": 1
}
```

> SAY: A document is similar to one record in a table. Projection returns only the fields we need. The deviceId identifies a device, while its location stores a longitude and latitude pair.

### B. Event evidence

Open events -> Documents. In Filter, paste:

```
{
  "eventType": "login_failed"
}
```

In Options -> Sort, paste {"ts": -1}, then click Find. Expand a fresh record and show deviceId, protocol, srcIp, ts, payload, prevHash, hash and chainSeq.

> SAY: This is one observed activity, not yet a complete investigation. The payload depends on its protocol. Each event also stores its device's previous hash and its own hash for later integrity verification.

> NOTE: Filter and Project accept objects. Sort accepts an object such as {"ts": -1}, where -1 means newest first. Aggregations accepts an array of stages. Do not paste a whole pipeline into the Documents Filter field.

## Page 5: 4. Rules, alerts and evidence links

Explain detection as data and trace a finding back to its records

### A. Stored detection rule

Open rules -> Documents. Paste this into Filter and click Find:

```
{
  "ruleId": "R-BRUTE-01"
}
```

1. Expand window, pipeline and trigger. Point out active, severity and cooldownSeconds.
2. Read its stages: match failed logins for the actor/device, group and count them, then require at least five failures.

> SAY: The rule is a MongoDB document containing an aggregation pipeline. The detector supplies the event context and time window, then MongoDB evaluates the query. A change stream refreshes the worker's rule cache after a rule edit.

### B. Detection result

Open alerts -> Documents. Filter by the same rule and sort by detection time:

```
{
  "ruleId": "R-BRUTE-01"
}
```

Sort: {"alertCreatedAt": -1}. Show actor, targetIp, deviceId, severity, eventIds, eventInsertedAt and alertCreatedAt.

> SAY: The alert records which rule matched and which event documents support it. Detection latency compares the insertion time with the alert creation time.

### C. Follow one event reference

Copy one ObjectId from the newest alert's eventIds array. In events, filter by {"_id": ObjectId("PASTE_THE_24_CHARACTER_ID")}. Replace only the quoted ID with the value you copied. Do not copy the literal placeholder.

> NOTE: Use a fresh alert for this step. An old alert can reference raw events that have already expired. Editable rule pipelines reject $out, $merge, $function and $lookup. Use the dashboard Rules editor to demonstrate controlled rule writes.

## Page 6: 5. Incidents, risk and transactions

Show how separate documents support one investigation

### A. Open a full incident document

Open incidents -> Documents. Use this Filter, set Sort to {"updatedAt": -1}, then click Find:

```
{
  "chain.0": {
    "$exists": true
  }
}
```

1. Expand chain. Read actor, targetIp, deviceId, ruleId and hop for the newly launched lateral scenario.
2. Show status and statusHistory. In the dashboard, move an open incident to triaged. Return to Compass and click Find to see the new history entry.

> SAY: MongoDB graph lookup follows the target IP of one alert to the actor IP of another. The application stores the ordered result inside the incident. Compass shows the evidence documents; the dashboard draws the graph.

### B. Open the calculated risk document

Open risk_scores. Filter by a deviceId from this incident, using {"deviceId":"PASTE_DEVICE_ID"}. Expand score, factors and calculatedAt. Choose a document with these fields rather than an old minimal test record.

> SAY: MongoDB calculates risk from the severity and age of recent alerts. The stored factors explain the score. The score is a snapshot and changes when scoring runs.

### Explain ACID in one sentence

> SAY: Incident creation, alert linking and risk updates use one multi-document transaction, so they commit together or roll back together. A status change updates status and history atomically within one incident document.

> NOTE: The valid status path is open -> triaged -> closed. Status history is embedded for convenient reads. Device IDs, rule IDs and event IDs act as references; MongoDB does not automatically enforce SQL-style foreign keys for these links.

## Page 7: 6. Run aggregation inside Compass

Two short examples that clearly demonstrate DBMS processing

1. Open the named collection, then click Aggregations.
2. Choose the </> Text mode and replace the editor contents with the complete pipeline array.
3. Click Run. In Stage mode instead, choose each stage separately and paste only its stage body.

### A. Count events by protocol - events collection

```
[
  {"$group":{"_id":"$protocol","eventCount":{"$sum":1}}},
  {"$sort":{"eventCount":-1}}
]
```

> SAY: The group stage puts events with the same protocol together and counts them. The sort stage displays the largest group first. MongoDB performs this calculation.

### B. Count detections by stage - alerts collection

```
[
  {"$group":{"_id":"$stage","alertCount":{"$sum":1}}},
  {"$sort":{"alertCount":-1}}
]
```

> SAY: This summary helps us see which types of suspicious activity produced alerts. It groups stored alert documents rather than recalculating detections.

> NOTE: The _id in a group result is the grouping key, such as ssh or credential-access. It is not an event ID. These read-only pipelines do not change the original documents. Empty output means the source query has no matching records.

## Page 8: 7. Indexes and query performance

Show what MongoDB examines to answer a query

### A. Explain the indexes already present

Open events -> Indexes. Point to the following entries:

| Index | Reason |
| --- | --- |
| events_device_ts | Filter one device and its event timestamps |
| events_src_ip_ts | Investigate an actor over a time range |
| events_type_ts | Find an event type over a time range |
| events_device_chain_seq_unique | Prevent duplicate sequence numbers within a device |
| events_ts_ttl | Expire raw events using the ts field |

Open devices -> Indexes to show unique deviceId and ip indexes, plus the location 2dsphere index.

### B. View an actual query plan

1. In events -> Documents, copy a deviceId from a retained event.
2. Filter with {"deviceId":"PASTE_DEVICE_ID"} and sort with {"ts":1}. Replace the placeholder with your real value.
3. Click Explain in the query bar. Inspect the Visual Tree and Query Performance Summary. Raw Output contains the detailed execution statistics.
4. Read the actual documents returned, documents examined, index keys examined and execution time.

> SAY: An index gives MongoDB an efficient way to locate selected records. IXSCAN means an index scan. COLLSCAN means a collection scan. I compare how much data the query examines, not only the elapsed time.

> NOTE: A small or cached dataset may show 0 ms. MongoDB can also choose a collection scan when it is cheaper. Do not promise an index plan or a speedup before inspecting the output. The copyable notes include a controlled hint comparison without dropping any index.

## Page 9: 8. Validation and retention

Demonstrate database constraints without changing the schema

### A. Show the validation rules

1. Open events -> Validation. Inspect the existing $jsonSchema definition.
2. Point to required fields such as ts, deviceId, protocol, payload, prevHash and hash.
3. Point to the protocol enum and payload shapes. The current validation level is strict and its action is error.

> SAY: The database rejects documents that break its validation rules. Pydantic checks API input first, and MongoDB provides another check at the storage layer.

### B. Optional negative test: a rejected insert

Only if you want a live constraints example: in events -> Documents, choose Add Data -> Insert Document and try this deliberately incomplete document:

```
{"deviceId":"compass-validation-demo"}
```

Expected result: document validation failure, commonly error code 121, because required fields are missing. Show the rejection and close the insert dialog. Do not change or disable the validator to accept it.

### C. Explain the TTL setting

In events -> Indexes, inspect events_ts_ttl. Its expireAfterSeconds value is 604800, which is seven days. It uses the event's ts field.

> SAY: TTL handles retention automatically. MongoDB deletes expired event records in the background, so deletion does not occur at the exact expiry second. Older alerts and incident snapshots can remain after raw events expire.

> NOTE: The Schema tab samples document shapes; the Validation tab shows enforced rules. These are different features. A missing old event is not automatically evidence of malicious deletion: retention expiry also removes data.

## Page 10: 9. Location queries and time-series data

Show two database features beyond ordinary document reads

### A. Nearby device query - devices -> Documents

Clear previous Sort and Project options. Paste this into Filter and click Find:

```
{
  "location": {
    "$near": {
      "$geometry": {
        "type": "Point",
        "coordinates": [
          77.5946,
          12.9716
        ]
      },
      "$maxDistance": 5000
    }
  }
}
```

> SAY: This returns devices within five kilometres of our Bengaluru centre. MongoDB uses the 2dsphere location index. GeoJSON stores coordinates in longitude, latitude order. The distance here is in metres.

The query already orders results by distance. It returns nearby inventory, including devices with no detected alert.

### B. Time-series rollups

Open device_telemetry. A rollup document contains ts, deviceId, eventCount, failedLogins and bytesOut. Its time field is ts, its metadata field is deviceId, and its granularity is minutes.

> SAY: Raw events contain individual observations. This time-series collection stores per-minute summaries for historical analysis and baselines.

> NOTE: device_telemetry may be empty. The rollup worker is implemented but is not a permanent Compose service. Start it separately during preparation only if you intend to demonstrate populated rollups. These writes stay outside incident transactions. The notes include the optional worker command and a metadata query.

## Page 11: 10. Integrity, users and replication

Optional supporting evidence using documents and the Compass shell

### A. Tamper evidence

In the dashboard Integrity page, Run 3-mode demo creates isolated edit/delete/swap chains. Refresh events in Compass and filter with {"deviceId":{"$regex":"^tamper-"}}. Point to the stored hash fields; use the Integrity page for the reported first broken position.

> SAY: MongoDB stores the event evidence and hashes. The Python checker recomputes each device chain to identify the first break. Hashing helps detect changes; it does not encrypt the event or make it tamper-proof.

### B. User records

Open users -> Documents. Use Filter {"username":{"$in":["admin","analyst"]}} and this Project:

```
{
  "_id": 0,
  "username": 1,
  "role": 1,
  "active": 1
}
```

Say: Application roles control dashboard actions. MongoDB service roles restrict database operations. Application analysts can advance incident status through the API; the database analyst principal has read-only access.

### C. Replica-set status - optional embedded shell

Open Compass's MongoDB shell control. Paste the following database command there, not in a Documents Filter:

```
rs.status().members.map(m => ({
  host: m.name,
  state: m.stateStr
}))
```

> SAY: A healthy run has one primary and two secondaries. They hold replicated copies of the database. All three run on this laptop, so this is a local availability demonstration.

> NOTE: The current Compass session connects directly to one member and does not automatically switch to another host during failover. Do not run an unprepared failover test in this walkthrough. Newest-event truncation detection requires a trusted external checkpoint.

## Page 12: 11. Quick speaking sheet

Use this page immediately before the presentation

| Show | Say |
| --- | --- |
| Database list | One application database contains eight main collections and two supporting collections. |
| devices | This is our virtual-device inventory. |
| events | These are raw observations and their integrity fields. |
| rules | Detection logic is stored as editable aggregation pipelines. |
| alerts | These findings reference the event evidence. |
| incidents | Related alerts form an ordered investigation chain. |
| risk_scores | These are calculated snapshots with explanatory factors. |
| Aggregation | MongoDB groups and counts data inside the database. |
| Indexes and Explain | We inspect the query plan and work performed. |
| Validation | The database rejects documents that break its constraints. |

### If something does not appear

Only three collections: check port 37017. ENOTFOUND mongo1/mongo2: enable Direct Connection and clear Replica Set Name in Compass. Authentication failed: re-enter the root password value from .env and use admin as the authentication database.

Empty events: clear filters and launch a fresh scenario. Missing fields: choose a full record using the provided filters. Empty telemetry: explain the separate rollup job. Old event reference not found: use a fresh alert because raw events expire.

### Closing words

> SAY: HoneyGraph demonstrates how a DBMS can validate and organize evidence, detect patterns with aggregation, follow relationships, and keep related updates consistent. Compass lets us inspect these database operations directly.

> NOTE: For five minutes: devices -> fresh events -> one rule and alert -> incident -> one aggregation -> Indexes. Use the longer sections only when time permits. Copyable queries and optional shell examples are supplied in the companion notes.

Reference: MongoDB Compass documentation, https://www.mongodb.com/docs/compass/. The companion notes include detailed source links and copyable commands.

## Copyable query index

### device_projection
Collection: `devices`. Paste into: **Project**.

```json
{
  "_id": 0,
  "deviceId": 1,
  "ip": 1,
  "type": 1,
  "protocol": 1
}
```

### failed_logins
Collection: `events`. Paste into: **Filter**.

```json
{
  "eventType": "login_failed"
}
```

### brute_rule
Collection: `rules`. Paste into: **Filter**.

```json
{
  "ruleId": "R-BRUTE-01"
}
```

### brute_alerts
Collection: `alerts`. Paste into: **Filter**.

```json
{
  "ruleId": "R-BRUTE-01"
}
```

### full_incidents
Collection: `incidents`. Paste into: **Filter**.

```json
{
  "chain.0": {
    "$exists": true
  }
}
```

### events_by_protocol
Collection: `events`. Paste into: **Aggregations / Text**.

```json
[
  {
    "$group": {
      "_id": "$protocol",
      "eventCount": {
        "$sum": 1
      }
    }
  },
  {
    "$sort": {
      "eventCount": -1
    }
  }
]
```

### alerts_by_stage
Collection: `alerts`. Paste into: **Aggregations / Text**.

```json
[
  {
    "$group": {
      "_id": "$stage",
      "alertCount": {
        "$sum": 1
      }
    }
  },
  {
    "$sort": {
      "alertCount": -1
    }
  }
]
```

### nearby_devices
Collection: `devices`. Paste into: **Filter**.

```json
{
  "location": {
    "$near": {
      "$geometry": {
        "type": "Point",
        "coordinates": [
          77.5946,
          12.9716
        ]
      },
      "$maxDistance": 5000
    }
  }
}
```

### user_projection
Collection: `users`. Paste into: **Project**.

```json
{
  "_id": 0,
  "username": 1,
  "role": 1,
  "active": 1
}
```

## Optional Compass shell commands

Paste these into the embedded MongoDB shell, not into a Documents filter. All commands in this section are read-only.

### List the collections and inspect storage options
```javascript
var hg = db.getSiblingDB("honeygraph");
hg.getCollectionNames();
hg.getCollectionInfos({name:"device_telemetry"})[0].options;
hg.events.getIndexes();
hg.getRole("ingest_svc", {showPrivileges:true});
rs.status().members.map(m => ({host:m.name, state:m.stateStr}));
```

### Trace the latest alert to its evidence without a placeholder
```javascript
var hg = db.getSiblingDB("honeygraph");
var latest = hg.alerts.find({eventIds:{$exists:true}}).sort({alertCreatedAt:-1}).limit(1).toArray()[0];
if (latest) {
  printjson(latest);
  printjson(hg.events.find({_id:{$in:latest.eventIds}}).toArray());
}
```

### Compare one indexed query with a collection scan
Choose a device that has retained events. These commands keep the same query and do not drop an index.
```javascript
var hg = db.getSiblingDB("honeygraph");
var sample = hg.events.findOne();
if (sample) {
  var q = {deviceId:sample.deviceId};
  printjson(hg.events.find(q).hint("events_device_ts").explain("executionStats"));
  printjson(hg.events.find(q).hint({$natural:1}).explain("executionStats"));
}
```

### Inspect graph traversal for a stored incident
The incident alert IDs scope this query. It follows the first stored edge and returns downstream alerts. The root edge itself is separate from `followingHops`. Graph output is not guaranteed to be sorted.
```javascript
var hg = db.getSiblingDB("honeygraph");
var investigation = hg.incidents.find({"chain.0":{$exists:true},"chain.stage":"lateral-movement"}).sort({updatedAt:-1}).limit(1).toArray()[0];
if (investigation) {
  printjson(hg.alerts.aggregate([
    {$match:{_id:investigation.chain[0].alertId}},
    {$graphLookup:{
      from:"alerts", startWith:"$targetIp",
      connectFromField:"targetIp", connectToField:"actor",
      maxDepth:5, depthField:"graphDepth", as:"followingHops",
      restrictSearchWithMatch:{_id:{$in:investigation.chain.map(a=>a.alertId)}}
    }},
    {$project:{actor:1,targetIp:1,ruleId:1,followingHops:1}}
  ]).toArray());
}
```

## Optional telemetry preparation
This launches the existing rollup worker in the detector container. Run it in a separate PowerShell terminal during preparation and leave it running. It aggregates the previous minute, so launch fresh scenarios while it runs and wait through a minute boundary. Ctrl+C ends this manually started worker. Recreating the container does not preserve the manually started worker.
```powershell
docker compose exec detector python -m workers.telemetry_rollup
```

The worker writes summary documents. It is not needed for the core Compass demo. A baseline for meaningful outgoing-byte comparison needs suitable normal telemetry, not only failed-login events.

## Sources checked

- Project source: mongo/init_db.py; mongo/seed_rules.py; backend/app/routers/scenarios.py and incidents.py; backend/workers/detector.py, chain_builder.py, risk_scorer.py, integrity_checker.py and telemetry_rollup.py.
- Project frontend and Makefile. Live database inspection confirmed the collection names, event index names and TTL setting. At preparation time, events and device_telemetry were empty. No traffic was generated by the guide builder.
- MongoDB Compass Documents: https://www.mongodb.com/docs/compass/documents/
- Query filters: https://www.mongodb.com/docs/compass/query/filter/
- Aggregation text mode: https://www.mongodb.com/docs/compass/create-agg-pipeline/
- Explain: https://www.mongodb.com/docs/compass/query-plan/
- Validation: https://www.mongodb.com/docs/compass/validation/
- Connection options: https://www.mongodb.com/docs/manual/reference/connection-string-options/