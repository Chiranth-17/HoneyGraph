# HoneyGraph: DBMS Presentation and Demo Guide

Prepared 19 November 2026. Existing implementation only.

## 1. HoneyGraph

A simple DBMS presentation and live demo guide

Explain the project through its data.

RVCE DBMS mini-project | Prepared 19 November 2026

| Team member | USN |
| --- | --- |
| CHIRANTH SUDHAKAR | 1RV24CY012 |
| CHIRAANTH S | 1RV24CY011 |
| MEGHASHYAM H PATIL | 1RV24CY030 |

Guide: Prof. L Kala Chandrashekhar, Assistant Professor

### Start with these exact words

> SAY: Good morning. Our project is HoneyGraph, a MongoDB-based system for understanding suspicious activity in a simulated IoT network. It stores device events, detects suspicious patterns, connects related alerts into an attack chain, and shows the affected devices on a dashboard.

> SAY: From the DBMS point of view, we demonstrate document modeling, schema validation, indexes, aggregation, change streams, graph queries, transactions, geospatial queries, access control, and replication. All traffic is simulated; no real device is attacked.

### The story to remember

Simulated traffic -> Events -> Alerts -> Incident -> Device risk

An event is a recorded activity. An alert means a rule found a suspicious pattern. An incident groups related alerts into one investigation.

> NOTE: Use pages 4-10 for the dashboard walkthrough. Pages 12-15 explain the database. Page 18 is your quick rehearsal sheet. This guide documents existing features; the proposed DBMS Lab is not part of this demo.

## 2. Prepare before the presentation

Do this before the evaluator arrives

1. Open Docker Desktop and wait until its engine is ready.
2. Open PowerShell in the project folder shown below.
3. Start the existing stack. Use seed only for first setup or intentional rule initialization.
4. Open the dashboard and sign in with your configured admin account.
5. Keep two dashboard tabs open: Live Alerts and Scenarios & Users. This makes live updates easy to show.
6. Check that the Rules page has active rules and Device Risk has device markers. Rehearse one Mirai and one lateral-movement launch.

```
Set-Location 'C:\Users\chira\OneDrive\Desktop\dbms(EL)'
mingw32-make up
docker compose ps
```

If your machine uses make instead, replace mingw32-make with make. For a fresh database, run mingw32-make seed after startup. Seeding initializes collections, users and rules; it does not create the 500-device inventory and may replace seeded rule edits.

| Open | Address / source |
| --- | --- |
| Dashboard | http://localhost:5173 |
| API documentation | http://localhost:18000/docs |
| Health check | http://localhost:18000/health |
| Admin credentials | APP_ADMIN_USERNAME / APP_ADMIN_PASSWORD in .env |
| Analyst credentials | APP_ANALYST_USERNAME / APP_ANALYST_PASSWORD in .env |

### Optional automation, outside the live talk

```
mingw32-make demo
```

This runs the headless acceptance flow and creates demo data. It does not replace a visual explanation. This guide does not claim the tests were rerun today.

> NOTE: Keep the existing database for the presentation. If the map is empty, use the inventory-only preparation in the editable notes supplied with this guide. Do not rerun initialization merely to fix an expired login.

## 3. Explain how the data is organized

Point to this model before opening the dashboard

> SAY: MongoDB stores documents inside collections. A collection is similar to a table, and a document is similar to a row. We separate raw observations, detection results and investigations because each has a different purpose.

| Collection | What it stores | Simple reason |
| --- | --- | --- |
| devices | ID, IP, type, firmware and location | One inventory record per device |
| events | Raw protocol activity and hashes | Evidence used for detection |
| device_telemetry | Per-minute device summaries | Time-series storage for rollups |
| rules | Editable aggregation pipelines | Detection logic stored as data |
| alerts | Rule matches and event references | Suspicious findings with evidence |
| incidents | Related alerts, chain and history | One investigation view |
| risk_scores | Score, factors and calculation time | Fast reading of calculated risk |
| users | Username, password hash and role | Application authentication |

Two supporting collections: system_state stores worker checkpoints and integrity results; ground_truth stores simulator labels for evaluation. Ground-truth labels are separate from event evidence.

### Explain the relationships

1. devices.deviceId connects one device to many events and alerts.
2. alerts.ruleId identifies the detection rule; alerts.eventIds links the evidence.
3. alerts.incidentId points to the investigation that contains the alert.
4. incidents embeds chain evidence and statusHistory for convenient detail reads.

> NOTE: MongoDB creates a unique _id for each document. Named identifiers such as deviceId and ruleId also have unique indexes. These references are application-managed links, not automatically enforced SQL foreign keys.

## 4. Demo 1 - Live Alerts

Show a new detection and explain where it came from

1. In tab A, open Live Alerts. Clear filters and click Apply. Check that the connection badge says live.
2. In tab B, open Scenarios & Users. Select mirai_bruteforce and click Launch once.
3. Return to tab A immediately. Point to the newly arriving alert rows and their detection times.
4. Read one row: rule ID, stage, device, actor IP, target IP, severity and latency.
5. Copy a device ID into the Device filter and click Apply to show a focused result. Clear it afterwards.

### Say this while the alert appears

> SAY: The simulator inserts login activity into the events collection. A MongoDB change stream informs the detector about each new insert. The detector runs the stored rule pipeline over the relevant time window. When the condition matches, it writes an alert.

> SAY: A second change stream watches alerts. The backend sends each new alert to the browser through a WebSocket, so the live feed updates without a manual reload.

### DBMS concepts to name

| Concept | What the evaluator can see |
| --- | --- |
| Change streams | A database insert starts processing |
| Aggregation | A rule counts or groups activity in a time window |
| Evidence references | An alert stores the IDs of its supporting events |
| Unique dedupe key | Repeated matches in a cooldown bucket are suppressed |

The Mirai-style scenario records a scan, failed logins, a successful login and command activity. These are synthetic records; no real login or command is executed.

> NOTE: Aim to show an alert in about one second, but quote the latency actually displayed. The live badge means the socket is connected; it does not mean traffic is always being generated. Use Apply to restore a filtered REST result: incoming socket rows are currently added to the feed regardless of its filter fields.

## 5. Demo 2 - Incidents and the graph

Connect individual detections into a multi-hop story

1. In Scenarios & Users, select lateral_movement and click Launch.
2. Wait for the job to complete, then click its Open incident link. Use the new job link rather than guessing which old incident is relevant.
3. Read the directed graph from left to right. Show the source, intermediate devices and final target.
4. Use Chain evidence to read the actual actor and target IPs in hop order.
5. Point out the rule and stage labels on the edges. A four-edge example has hops 0, 1, 2 and 3.

> SAY: An alert tells us about one suspicious finding. An incident connects findings that belong to the same investigation. Here, one device becomes the source of activity against the next device, so we can follow the path.

> SAY: MongoDB performs the traversal with $graphLookup. The target IP of one alert is matched with the actor IP of a later connected alert. A reverse traversal helps find the starting point. We then order the returned evidence for display.

Source -> Device A -> Device B -> Device C -> Device D

### Explain what the picture means

| Visual | Meaning |
| --- | --- |
| Node | An IP address or device |
| Directed edge | An alert linking an actor to a target |
| Hop | The position of an alert in the reconstructed path |
| Several same-source edges | Parallel detections may belong to one incident |

> NOTE: The graph is a correlation of observed evidence. It does not prove that a real exploit succeeded. Time bounds, a traversal-depth limit and duplicate handling constrain reconstruction. Current dashboard launches build incidents after their alerts are processed; external ingestion uses the standalone builder.

## 6. Demo 3 - Transactions and status history

Explain the two different update mechanisms correctly

### A. Incident creation: a multi-document transaction

> SAY: Creating an incident changes three related collections: incidents, alerts and risk_scores. These changes must agree. We put them in one transaction, so the database commits them together or rolls them back together.

| ACID property | Simple HoneyGraph explanation |
| --- | --- |
| Atomicity | Incident, alert links and risk updates succeed together |
| Consistency | The transaction and application rules keep related state aligned |
| Isolation | Snapshot reads give the transaction a consistent database view |
| Durability | Majority acknowledgement is requested for the incident transaction |

### B. Status change: one atomic document update

1. Open the new incident while its status is open.
2. Click Mark triaged. Explain that an analyst has started the investigation.
3. Click Mark closed. Explain that the investigation has been completed.
4. Read Status history: open, triaged and closed, with recorded times and update users.

> SAY: Status updates change one incident document. MongoDB updates the status and appends the history entry in the same atomic operation. The update also checks the previous status, so concurrent requests cannot silently record the same transition twice.

Allowed path: open -> triaged -> closed. Skipping from open directly to closed is rejected with HTTP 409. The UI only offers the valid next action.

> NOTE: There is no transaction rollback button in the present dashboard. Explain rollback using the existing automated transaction tests if asked. Status history is an investigation record, not an immutable database-wide audit log. Closing an incident does not automatically erase its alert evidence or reset risk.

## 7. Demo 4 - Rules that take effect live

Show detection logic stored as database documents

1. As admin, open Rules. Click an existing rule and briefly show its JSON pipeline and hit count.
2. Click New rule. Keep its generated unique rule ID and change the name to Presentation login-failure rule.
3. Use the pipeline below and click Validate & publish. Wait a moment for the live cache refresh.
4. Launch a new mirai_bruteforce scenario, then open Live Alerts. Find the alert with your new rule ID.
5. Return to Rules and refresh the page to see updated hit counts. Disable your presentation rule after the demo.

```
[
  {"$match": {
    "_id": "{{eventId}}",
    "eventType": "login_failed"
  }},
  {"$limit": 1}
]
```

> SAY: This rule is a document in the rules collection. The placeholder eventId is replaced with the current event identifier. MongoDB runs the pipeline. A change stream on rules refreshes the detector cache, so publishing the rule does not require a restart.

This demonstration rule matches a single failed login so its effect is easy to see. The seeded brute-force rule uses a threshold; one failed login alone is not proof of an attack.

### Show validation without changing a working rule

Click New rule again. Replace its pipeline with [{"$out":"demo_rejected"}] and click Validate & publish. Show the rejection. It should not be saved or executed.

> SAY: Only approved read-only stages are accepted. Operators such as $out, $merge and $function are rejected to prevent a detection rule from writing data or executing custom code.

> NOTE: The rule validator also rejects $lookup in editable rule pipelines. Trusted backend $graphLookup is a separate controlled path. The live-cache label is a UI indicator; the new matching alert is your evidence that the change was applied.

## 8. Demo 5 - Device Risk Map

Explain both geospatial queries and database aggregation

1. After the scenario finishes, open Device Risk. If it was already open, click Search radius to reload its data.
2. Choose a radius such as 25 km and click Search radius. Point to the returned device count.
3. Reduce the radius, for example to 5 km, and search again. Explain that the database performs the location filter.
4. Select an affected device marker. Read its score, top factors and recent event timeline.

> SAY: Each device stores its location as a GeoJSON Point. MongoDB uses a 2dsphere index and a $near query to return devices within the selected distance from Bengaluru.

| Stored location | Map location |
| --- | --- |
| GeoJSON: [longitude, latitude] | Leaflet display: [latitude, longitude] |
| Radius passed to the API | Distance in metres |
| Current query centre | Bengaluru: longitude 77.5946, latitude 12.9716 |

### Explain the risk score simply

> SAY: Risk combines the severity of recent alerts. Newer alerts contribute more; older alerts contribute less. MongoDB calculates the contributions using aggregation, adds them and caps the result at 100. The factors chart explains which alerts contributed most.

The calculation considers the previous 24 hours. By default, one alert contribution halves after six hours when recalculated. Scores are stored snapshots and update when scoring runs; they do not continuously decrease while you watch the page.

| Colour | Current score range |
| --- | --- |
| Cyan | Below 35 |
| Amber | 35 to below 70 |
| Red | 70 or more |

> NOTE: An attacked device can remain cyan if its total score is low. The radius query returns nearby inventory, including devices without alerts; it is not a compromised-only filter. The background map tiles need internet, while the location query uses the local database.

## 9. Demo 6 - Log integrity

Demonstrate detection of changes to stored evidence

1. Open Integrity. For a quick clean check, enter one known clean, recently generated device ID and click Run check.
2. As admin, click Run 3-mode demo. The helper creates three isolated test chains and changes them deliberately.
3. Point to the new tamper-edit, tamper-delete and tamper-swap device IDs in the results.
4. Read the first broken position and reason for each new chain. The helper targets position 3.
5. Explain the expected and stored hash columns. If the table also contains older test results, focus on the new demo IDs.

> SAY: Each device has its own hash chain. The hash of an event depends on the previous hash and the canonical event fields. If a stored event is edited, removed or reordered, the checker can find the first place where the chain no longer agrees.

```
hash = SHA256(previous_hash + canonical_event_json)
First event: previous_hash = 64 zero characters
```

| Demo action | Expected report |
| --- | --- |
| Edit the third event | Position 3, modified |
| Delete the third event | Position 3, missing |
| Swap the third and fourth event times | Position 3, reordered |

### Why one chain per device?

Different devices can be ingested independently. One device does not need to wait for a global chain position. Canonical JSON uses sorted keys and UTC timestamps with fixed millisecond precision.

> NOTE: Call this tamper-evident, not tamper-proof or encrypted. A trusted external checkpoint is needed to detect deletion of the newest suffix; the current Integrity page checks live links and does not compare external anchors. Retention expiry can also remove old evidence, so a missing link needs investigation before you call it malicious tampering.

## 10. Demo 7 - Users, login and permissions

Distinguish application roles from MongoDB roles

1. As admin, open Scenarios & Users and point to the account-management panel.
2. If time permits, create a uniquely named analyst account using an 8+ character password. Do not display the password during the presentation.
3. Sign out and sign in as analyst. Show that Rules and Scenarios & Users are absent from the navigation.
4. Explain that backend authorization also checks permissions; hiding a menu alone is not security.
5. Sign out and return to admin for the final part of the demo.

> SAY: Authentication checks who the user is. Authorization checks what that user may do. Passwords are stored as bcrypt hashes. After login, the client receives a signed JWT, and protected endpoints verify it.

| Application role | Allowed actions |
| --- | --- |
| Admin | View data; manage rules and accounts; launch scenarios; run tamper demos |
| Analyst | View alerts, incidents and risk; run integrity checks; advance incident status |

### MongoDB service permissions are another layer

| Database principal | Purpose |
| --- | --- |
| ingest_svc | Insert events and read chain heads |
| detect_svc | Read inputs; write detection and correlation results |
| rule_admin | Manage rule documents through the controlled write path |
| analyst | Read-only database access |
| tamper_demo | Update/delete events for the controlled demo |
| api_svc | Read dashboard data and perform permitted API updates |

> NOTE: The MongoDB analyst principal is read-only. The application analyst account can update incident status through the API service account. They are different layers. An expired JWT requires signing in again; it does not mean MongoDB is offline.

## 11. Explain the seven simulated scenarios

Show two live; explain the others briefly

| Scenario | Simple explanation | DBMS connection |
| --- | --- | --- |
| mirai_bruteforce | Repeated failed logins followed by later activity | Windowed counts and event sequences |
| recon | One source contacts many devices | Grouping and distinct-device counts |
| credential_stuffing | One source tries many usernames over HTTP | Distinct-value aggregation |
| mqtt_abuse | An unapproved client publishes control activity | Stored allow-list detection logic |
| lateral_movement | An internal device becomes the source of the next hop | $graphLookup over alert relationships |
| exfil_burst | Outgoing bytes rise far above normal | Comparison with telemetry averages |
| log_tamper | Stored records are deliberately changed | Integrity checking of hash chains |

> SAY: These scenarios generate abstract event records. Their purpose is to test storage, queries, detection and correlation. They do not contain working attack tools.

### A sensible live-demo choice

Use Mirai to explain change streams and aggregation. Use lateral movement to explain graph traversal and incidents. Use the Integrity page's Run 3-mode demo for the clearest edit/delete/swap demonstration.

### Conditions to mention honestly

1. A disabled rule, a cooldown bucket or missing baseline can mean no new alert. Read the job message rather than inventing a result.
2. The exfiltration detector needs historical device_telemetry to calculate an average. New raw events alone do not create that baseline.
3. A rollup worker is implemented but is not an always-running service in the current Compose file. Start it separately when rehearsing the extended baseline demo.
4. The simulator CLI stores evaluation labels in ground_truth; current dashboard launch jobs do not persist those labels.

> NOTE: Scenario job cards are kept in backend memory and reset after a backend restart. Persisted events, alerts and incidents are stored in MongoDB.

## 12. DBMS demonstration - queries and indexes

Optional terminal explanation after the dashboard

From the project root run mingw32-make mongosh. The target opens an authenticated shell without placing a password in this guide. Select the application database:

```
use honeygraph
show collections
db.devices.estimatedDocumentCount()
db.events.getIndexes()
```

### 1. Read the latest alert and its evidence

```
var latestAlert = db.alerts.find().sort({alertCreatedAt:-1}).limit(1).toArray()[0];
printjson(latestAlert);
if (latestAlert) {
  printjson(db.events.find({_id: {$in: latestAlert.eventIds}})
    .limit(5).toArray());
}
```

### 2. Explain a device query

```
var sampleDevice = db.devices.findOne();
if (sampleDevice) {
  var q = {deviceId: sampleDevice.deviceId,
    ts: {$gte: new Date(Date.now() - 86400000)}};
  printjson(db.events.find(q).hint("events_device_ts")
    .explain("executionStats"));
}
```

> SAY: A compound index on deviceId and ts helps MongoDB locate one device's events in a time range. In the execution statistics, I look at the plan, documents examined, keys examined and execution time. These explain how much work the query performed.

For a controlled comparison, run the same query with hint({$natural: 1}) and compare the results. Keep the query and dataset unchanged. No index needs to be dropped.

> NOTE: Choose a device with retained events. An empty query is a poor demonstration of useful indexing. Tiny or warm-cache datasets may show 0 ms for both plans; documents examined is still meaningful. Indexes speed selected reads but use disk space and add write work.

## 13. DBMS demonstration - validation and storage

Show constraints, retention and time-series design

### 1. Schema validation

```
db.getCollectionInfos({name: "events"})[0].options.validator
```

> SAY: MongoDB is flexible, but this project still enforces structure. The database checks required event fields, allowed protocol values and payload shapes. Pydantic validates API input first; MongoDB validation is the second line of defence.

Rules and alerts also have strict validators. Protocol-specific API validation ties each event to the correct payload. Unique indexes protect identifiers such as deviceId, device IP, ruleId and username.

### 2. TTL retention

```
db.events.getIndexes().filter(
  i => i.expireAfterSeconds !== undefined
)
```

> SAY: The TTL index expires old events using their event timestamp. It supports automatic retention and limits database growth. The configured default is seven days. MongoDB removes expired records in the background, so deletion is not instantaneous.

### 3. Regular events and time-series rollups

```
db.getCollectionInfos({name: "device_telemetry"})[0].options
db.device_telemetry.find().sort({ts: -1}).limit(3)
```

| events | device_telemetry |
| --- | --- |
| Individual observations | Per-minute summaries |
| Regular collection | Time-series collection |
| Watched by the detector | Used for historical baseline queries |
| Contains raw evidence and hashes | Contains eventCount, failedLogins and bytesOut |

> NOTE: Time-series writes are kept outside incident transactions. In MongoDB 7.0, time-series collections cannot be used as the detector's watched collection or written in a multi-document transaction. An empty telemetry result means no retained rollups are available; do not claim the rollup scheduler is running automatically.

## 14. DBMS demonstration - replication

Explain availability and write acknowledgement

### Show the three members

```
rs.status().members.map(m => ({
  name: m.name,
  state: m.stateStr,
  health: m.health
}))
```

Expected healthy state: one PRIMARY and two SECONDARY members. Their names are mongo1, mongo2 and mongo3; any eligible member can become the primary.

> SAY: A replica set maintains copies of the same data. The primary accepts writes and secondaries replicate changes. If the primary becomes unavailable, the remaining eligible members can elect a new primary.

### Explain the durability trade-off

| Write policy | Where HoneyGraph uses it | Meaning |
| --- | --- | --- |
| w:1 | Bulk event ingestion | The primary acknowledges; a recently acknowledged write may be rolled back during failover |
| w:majority | Alerts and incident transactions | Acknowledgement waits for a voting majority, giving stronger failover durability |

### Three important distinctions

1. Replication gives copies and availability. It is not sharding: this prototype does not distribute separate portions of the dataset across shards.
2. All three nodes run on one laptop. If the laptop stops, all three stop; this is not three-machine disaster recovery.
3. Replication is not an independent backup. An unwanted deletion can be replicated too.

### Worker recovery

> SAY: The detector stores a change-stream resume token in system_state. After a restart it attempts to continue from that checkpoint, provided the required oplog history still exists. Dedupe keys reduce duplicate alert inserts during repeated processing.

> NOTE: Do not stop the primary in the main presentation unless you have rehearsed that optional test. A resume token is not a guarantee of exactly-once processing or zero data loss. Present measured failover results with their test conditions.

## 15. Explain normalization and document modeling

Connect your report tables to the actual MongoDB implementation

> SAY: Our report uses relational tables to explain normalization. The running application stores MongoDB documents. We use normalization to reason about repetition and dependencies, then choose references or embedding based on how the application reads data.

| Stage | HoneyGraph example | What improves |
| --- | --- | --- |
| UNF | One investigation record repeats device details, rule details and a list of events | Shows repeating groups and duplicated master data |
| 1NF | Represent repeated alert-event links as separate rows in a conceptual AlertEvents table | Each relational cell has one value |
| 2NF | For key (alertId, eventId), keep event details in Events and alert details in Alerts | Non-key fields depend on the whole composite key |
| 3NF | Keep device master details in Devices and rule definitions in Rules | Avoid unnecessary dependencies through other non-key fields |

### Use these conceptual relations in the explanation

```
Devices(deviceId PK, ip UNIQUE, type, firmware, location)
Events(eventId PK, deviceId REF, ts, protocol, payload, hash)
Rules(ruleId PK, name, severity, pipeline, active)
Alerts(alertId PK, deviceId REF, ruleId REF, incidentId REF)
AlertEvents(alertId REF, eventId REF)   -- composite PK
Incidents(incidentId PK, status, createdAt)
IncidentAlerts(incidentId REF, alertId REF, hop)
```

PK means primary key. REF means a relationship reference in this explanation; MongoDB does not automatically enforce these links as SQL foreign keys.

### Why is some data embedded?

> SAY: An incident is normally read together with its chain and status history, so those items are embedded. An alert also keeps the stage and severity recorded at detection time. This preserves historical evidence even if a rule is edited later.

> NOTE: AlertEvents and IncidentAlerts are conceptual report tables, not extra collections in the running project. Keeping historical snapshots is an intentional modeling choice. Do not claim that every MongoDB document is a fully normalized SQL table.

## 16. Simple viva answers

Use short answers first; expand only when asked

| Question | Answer you can say |
| --- | --- |
| Why MongoDB? | Our events have different protocol payloads. MongoDB supports documents, aggregation, change streams, graph traversal and geospatial queries in the same database. A relational design would also be possible. |
| Is MongoDB schema-less? | It supports flexible documents, but our important collections have database validators and unique indexes. |
| What is an aggregation pipeline? | A sequence of data-processing stages, such as filtering events, grouping by actor and counting failures. |
| What is a change stream? | A database notification mechanism that lets our worker react to inserted events without repeatedly scanning the whole collection. |
| Why not one big collection? | Devices, raw events, rules and incidents have different lifecycles. Separating them reduces unnecessary repetition and makes queries clearer. |
| Why use transactions? | One incident operation updates multiple collections. A transaction prevents a half-created incident with mismatched links or risk. |
| Does MongoDB enforce foreign keys? | Not for these references. The application maintains relationships, and transactions keep related writes together. |
| How do you avoid duplicate alerts? | A unique dedupe key includes the rule, actor, device and cooldown time bucket. Duplicate inserts are rejected. |
| Why store risk_scores? | It is a calculated snapshot for fast dashboard reads. It must be recalculated as evidence or time changes. |
| Does hashing encrypt the logs? | No. A hash helps detect a change; it does not hide the original event or make tampering impossible. |

> NOTE: If asked to prove an answer, point to the collection, query, index, rule pipeline or transaction code involved. A visible dashboard result is stronger when you can explain the database operation behind it.

## 17. Troubleshooting and honest claims

Keep the demo calm and explain the limits clearly

| What happens | What to do or explain |
| --- | --- |
| Live Alerts says offline | Check the login session first. Sign in again if expired. Then check backend and detector containers. |
| No new alert | Clear filters, launch once, inspect the job result, check active rules and cooldown. Do not assume the socket generates traffic. |
| No incident yet | Wait for the job to finish. Open its incident link. Incident materialization waits for detector processing; list polling is about 3 seconds. |
| Map appears unchanged | Click Search radius to reload. Check the selected device score. A low score can remain cyan after an attack. |
| No map markers | Check inventory first. Seeding schemas and rules does not seed the 500 devices. |
| Extra integrity failures | Identify the new isolated demo device IDs. Older tamper tests, retention expiry or out-of-order history need separate investigation. |
| New rule has no hits | Wait for the cache refresh, generate new matching traffic and refresh the Rules page. Check the exact new rule ID in alerts. |

### Do not overstate benchmark results

Quote a number only with its workload and measurement conditions. Direct bulk-insert throughput is different from full API throughput with validation, hashing and detection. One fast alert is not a p95 measurement.

The current quality benchmark uses a simplified evaluation path and does not establish production-wide 100% precision or recall. A successful election also does not prove that every in-flight event or alert survived failover.

### Useful health checks

```
docker compose ps
docker compose logs --tail 50 detector
Invoke-RestMethod http://localhost:18000/health
```

> NOTE: Rehearse with fresh events. Old simulator timestamps may be outside the retention or scoring window. Dashboard launches now use the current clock; deterministic CLI fixtures keep their fixed test clock.

## 18. Your 12-minute presentation sheet

Read this once immediately before you begin

| Time | Show | Main sentence |
| --- | --- | --- |
| 0:00-1:00 | Project introduction | We turn simulated IoT activity into evidence, detections and investigations. |
| 1:00-2:00 | Data model | Each collection has one main responsibility, linked by identifiers. |
| 2:00-3:30 | Mirai + Live Alerts | Change streams trigger processing; aggregation detects patterns. |
| 3:30-5:00 | Lateral incident | $graphLookup follows actor-to-target connections across devices. |
| 5:00-6:00 | Incident history | Related writes use a transaction; status and history update atomically. |
| 6:00-7:30 | New live rule | Detection logic is stored as validated data and changes without restart. |
| 7:30-8:30 | Device Risk | A geospatial index finds nearby assets; aggregation explains risk. |
| 8:30-10:00 | Integrity demo | A per-device hash chain identifies the first broken link. |
| 10:00-11:00 | Analyst login | Both the API and MongoDB restrict access to their permitted actions. |
| 11:00-12:00 | Indexes / conclusion | Indexes improve selected queries; replication supports availability. |

### If only five minutes are available

Introduction -> Mirai live alert -> lateral graph -> transaction explanation -> tamper demo -> conclusion. Keep normalization, replica details and the remaining scenarios for questions.

### Closing words

> SAY: HoneyGraph shows how database features can support a security application. MongoDB stores and validates the evidence, detects patterns with aggregation, follows relationships with graph lookup, and keeps related incident updates consistent with transactions. The dashboard makes these database results easy to understand.

> SAY: Our main learning is that a DBMS does more than store records. It can enforce structure, react to changes, process relationships and support reliable application workflows.

> NOTE: Presentation habit: for every screen, say what data is stored, what database operation runs, and why that operation is useful. Use the actual output on screen rather than memorizing fixed counts or timings.

## Inventory-only preparation (only when devices is empty)

From the project root, run the following in PowerShell. It uses your local .env, preserves a non-empty inventory and writes no event evidence. Run this during preparation, not while presenting.

```powershell
@'
import os, sys
sys.path.insert(0, 'backend')
from dotenv import load_dotenv
from pymongo import MongoClient
from simulator.devices import generate_devices, upsert_devices
load_dotenv()
with MongoClient(os.environ['MONGODB_URI']) as client:
    db = client[os.getenv('MONGO_DATABASE', 'honeygraph')]
    if db.devices.estimated_document_count() == 0:
        upsert_devices(db, generate_devices(500, 42))
    print('Inventory devices:', db.devices.estimated_document_count())
'@ | python
```

## Implementation sources used

- frontend/src/App.jsx and frontend/src/pages/*.jsx
- mongo/init_db.py and mongo/seed_rules.py
- backend/app/routers/ and backend/app/ingestion.py
- backend/workers/detector.py, chain_builder.py, risk_scorer.py, telemetry_rollup.py and integrity_checker.py
- backend/benchmarks/ingest.py, quality.py and demo_flow.py
- docker-compose.yml, Makefile, docs/CONTEXT.md and docs/PROGRESS.md

This document was checked against source code. It is a presentation guide, not a new execution report or fresh benchmark run.