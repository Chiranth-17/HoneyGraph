# HoneyGraph System Architecture

HoneyGraph is a defensive security and threat intelligence engine designed natively on MongoDB 7.0+. It provides real-time event ingestion, cryptographic tamper evidence, change-stream-driven threat detection, graph-based attack-chain reconstruction, and SOC analyst visualization for IoT environments.

---

## 1. Layered Architecture

HoneyGraph is structured into six discrete, decoupled architectural tiers:

```mermaid
graph TD
    classDef source fill:#f1f5f9,stroke:#64748b,stroke-width:2px,color:#0f172a;
    classDef ingest fill:#e0f2fe,stroke:#0284c7,stroke-width:2px,color:#0f172a;
    classDef data fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#0f172a;
    classDef detect fill:#ffedd5,stroke:#ea580c,stroke-width:2px,color:#0f172a;
    classDef api fill:#ede9fe,stroke:#7c3aed,stroke-width:2px,color:#0f172a;
    classDef ui fill:#fce7f3,stroke:#db2777,stroke-width:2px,color:#0f172a;

    subgraph Tier1["1. Data Source Tier"]
        S1["Simulated IoT Devices (MQTT/CoAP)"]:::source
        S2["Honeypots (Cowrie SSH/Telnet)"]:::source
        S3["Simulated Attack Scenarios"]:::source
    end

    subgraph Tier2["2. Ingestion Tier"]
        ING["FastAPI Ingestion Endpoint (/api/ingest)"]:::ingest
        HC["Per-Device SHA-256 Hash Chainer"]:::ingest
        WC["Bulk Ingestion Engine (w:1 acknowledgment)"]:::ingest
    end

    subgraph Tier3["3. Data Tier (MongoDB 7.0 Replica Set rs0)"]
        EV["events (Regular Collection)"]:::data
        TEL["device_telemetry (Time-Series Collection)"]:::data
        DEV["devices (Inventory & Geospatial)"]:::data
        RUL["rules (JSON Aggregation Pipelines)"]:::data
        ALT["alerts (Detected Threats)"]:::data
        INC["incidents (Graph Attack Chains)"]:::data
        RSK["risk_scores (Decayed Node Risk)"]:::data
        SYS["system_state (Tokens & Checkpoints)"]:::data
    end

    subgraph Tier4["4. Detection & Analytics Tier"]
        CS["Change Stream Listener (resume tokens)"]:::detect
        DET["Rule Evaluator (Safe Aggregations)"]:::detect
        CB["Chain Builder Worker ($graphLookup)"]:::detect
        SC["Risk Scorer Worker (Half-Life Decay)"]:::detect
        IC["Integrity Verifier (Chain Auditing)"]:::detect
    end

    subgraph Tier5["5. API Tier"]
        AUTH["JWT / bcrypt Auth Router"]:::api
        REST["SOC Management REST Routers"]:::api
        WS["Authenticated WebSocket Hub"]:::api
    end

    subgraph Tier6["6. Presentation Tier"]
        DASH["React 18 + Vite SOC Dashboard"]:::ui
        VIS["vis-network Attack Graph"]:::ui
        MAP["Leaflet Geospatial Risk Map"]:::ui
        CHART["Recharts Metric Visualizations"]:::ui
    end

    S1 -->|HTTP POST| ING
    S2 -->|HTTP POST| ING
    S3 -->|HTTP POST| ING
    ING --> HC --> WC --> EV
    EV -->|Oplog Change Stream| CS
    CS --> DET
    RUL -.->|Pipelines| DET
    DET -->|w:majority| ALT
    ALT --> CB
    CB -->|$graphLookup BFS| INC
    CB -->|Multi-doc Transaction| RSK
    EV -->|Periodic 1m Rollup| TEL
    ALT --> WS
    WS --> DASH
    REST --> DASH
    DASH --> VIS
    DASH --> MAP
    DASH --> CHART
```

### Tier Responsibilities

1. **Data Source Tier**: Simulated IoT hardware sensors, telemetry emitters, and Cowrie honeypots executing protocols across MQTT, CoAP, HTTP, SSH, and Telnet.
2. **Ingestion Tier**: High-throughput FastAPI endpoint. Maintains per-device cryptographic hash heads and performs bulk unordered inserts with `w:1` write concern.
3. **Data Tier**: 3-node MongoDB replica set (`rs0`) with internal keyFile authentication and custom least-privilege RBAC roles.
4. **Detection and Analytics Tier**: Asynchronous workers subscribing to change streams on `events` and `alerts`. Evaluates rules directly inside MongoDB via aggregation pipelines, reconstructs attack paths using `$graphLookup`, and applies exponential risk decay.
5. **API Tier**: Role-aware FastAPI application enforcing JWT bearer tokens with granular roles (`admin`, `analyst`) and WebSocket notification channels.
6. **Presentation Tier**: Modern React 18 single-page application rendering real-time push alerts, topological attack graphs, geospatial risk maps, and historical audit logs.

---

## 2. Document Model & Relationships

```mermaid
erDiagram
    devices ||--o{ events : "produces"
    devices ||--o{ device_telemetry : "telemetry rollup"
    devices ||--o{ risk_scores : "assessed"
    rules ||--o{ alerts : "triggers"
    events ||--o{ alerts : "evidence"
    alerts }o--o{ incidents : "correlated into"
    users ||--o{ incidents : "triaged by"

    devices {
        string deviceId PK
        string hostname
        string deviceType
        string ip
        object location "GeoJSON Point"
        string firmware
        string status
    }

    events {
        ObjectId _id PK
        date ts "TTL Index"
        string deviceId FK
        string protocol
        string eventType
        string srcIp
        object geo "GeoJSON Point"
        object payload "Polymorphic subdoc"
        string prevHash "SHA-256 link"
        string hash "SHA-256 digest"
        int chainSeq
    }

    alerts {
        ObjectId _id PK
        string ruleId FK
        string ruleName
        int severity
        string stage
        string actor
        string deviceId FK
        date ts
        date alertCreatedAt
        date eventInsertedAt
        double detectionLatencyMs
        array eventIds "References events._id"
    }

    incidents {
        ObjectId _id PK
        string title
        string status "open | triaged | closed"
        int severity
        date createdAt
        date updatedAt
        array alertIds "References alerts._id"
        array hops "Ordered graph nodes"
        array statusHistory "Embedded audit trail"
    }

    rules {
        ObjectId _id PK
        string ruleId UK
        string name
        string stage
        int severity
        string type "windowed | distinct | sequence | allowlist | baseline"
        object window
        object trigger
        array pipeline "Safe Aggregation Pipeline"
        int cooldownSeconds
        boolean active
    }

    device_telemetry {
        date ts "Time Field"
        string deviceId "Metadata Field"
        double cpu
        double memory
        double temperature
        int eventCount
    }

    risk_scores {
        string deviceId PK
        double currentScore
        double peakScore
        date lastCalculated
        int contributingAlerts
    }
```

### Embedded vs. Referenced Rationale

| Data Relationship | Modeling Choice | Engineering Justification |
|---|---|---|
| **Event Payloads** | **Embedded** | IoT telemetry varies by protocol (`ssh` auth has `{user, attempts}`, `mqtt` has `{topic, clientId, action}`). Embedding polymorphic payloads within `events` allows self-contained atomic ingestion with zero JOIN overhead. |
| **Incident Status History** | **Embedded** | Status transitions (`open -> triaged -> closed`) include timestamp, status, and actor. Because an incident transitions fewer than 10 times in its lifecycle, embedding guarantees that the complete audit history is loaded in a single read. |
| **Alert to Events** | **Referenced (`eventIds: [ObjectId]`)** | Alerts reference 1 to 20 triggering events. Referencing keeps the `alerts` collection lightweight, prevents document unbounded growth, and allows independent query access. |
| **Incident to Alerts** | **Referenced (`alertIds: [ObjectId]`)** | Multiple alerts across multiple devices form an incident. Storing an array of alert ObjectIDs avoids duplicating full alert bodies. |
| **Device to Events** | **Referenced (`deviceId`)** | A single IoT device produces millions of events over its lifetime. Embedding events inside a device document would violate the 16 MB BSON limit within minutes. |

---

## 3. Indexing Strategy & Performance Rationale

```mermaid
graph LR
    classDef idx fill:#f0fdf4,stroke:#16a34a,stroke-width:1px,color:#14532d;
    I1["(deviceId, ts) Compound Index"]:::idx -->|Per-device timeline & hash verification| E1[events]
    I2["(srcIp, ts) Compound Index"]:::idx -->|Attacker IP activity range| E1
    I3["(eventType, ts) Compound Index"]:::idx -->|Protocol & attack type timeline| E1
    I4["ts 2dsphere Geospatial Index"]:::idx -->|Spatial radius clustering| E1
    I5["ts TTL Index (7 days / 180 days)"]:::idx -->|Automated compliance pruning| E1
    I6["(actor, ts) Compound Index"]:::idx -->|Attacker alert history| A1[alerts]
    I7["ruleId Unique Index"]:::idx -->|Idempotent rule deployments| R1[rules]
```

### Index Rationale & Measured Benchmark Stats

1. **`{deviceId: 1, ts: 1}` on `events`**:
   * *Purpose:* Powers per-device forensic timelines and hash-chain verification.
   * *Measured Result:* Query scan on 1M events dropped from **611 ms** (1,000,000 docs examined) to **9 ms** (2,000 docs examined).
2. **`{srcIp: 1, ts: 1}` on `events`**:
   * *Purpose:* Enables rapid tracking of attacker IP activity across the entire fleet.
   * *Measured Result:* Query time dropped from **574 ms** to **14 ms**.
3. **`{eventType: 1, ts: 1}` on `events`**:
   * *Purpose:* Optimizes rule engine window evaluations for specific event triggers.
   * *Measured Result:* Query time dropped from **658 ms** to **9 ms** (3,334 docs examined).
4. **`{location: "2dsphere"}` on `devices` & `{geo: "2dsphere"}` on `events`**:
   * *Purpose:* Executes `$geoWithin` and `$centerSphere` spherical distance queries to identify compromised IoT hardware within geographic radius boundaries.
5. **`{ts: 1}` with `expireAfterSeconds`**:
   * *Purpose:* Automatic event purging to enforce CERT-In retention rules (default 7 days for dev, 180 days for production) without cron jobs. Indexes are updated dynamically using `collMod`.
6. **`{ruleId: 1}` Unique on `rules` & `{username: 1}` Unique on `users`**:
   * *Purpose:* Guarantees identity uniqueness and supports idempotent bulk rule deployments (`ReplaceOne(..., upsert=True)`).

---

## 4. Time-Series vs. Change-Streams vs. Transactions

### The MongoDB 7 Limitation

In MongoDB 7.0, **Time-Series collections do not support Change Streams or Multi-Document ACID Transactions**:
1. *Change Streams:* MongoDB stores time-series data internally in compressed columnar buckets (`system.buckets.collection_name`). The change-stream engine cannot listen on bucket compaction.
2. *Transactions:* Writes into time-series collections cannot be executed inside a multi-document session transaction.

### HoneyGraph's Architectural Workaround

```mermaid
graph TD
    classDef reg fill:#dbeafe,stroke:#1d4ed8,stroke-width:2px;
    classDef ts fill:#fef3c7,stroke:#d97706,stroke-width:2px;

    IN[Incoming Ingestion Stream] -->|High-Rate Raw Events| REG[events: Regular Collection]:::reg
    REG -->|Change Streams Enabled| DET[Change Stream Detector Worker]
    REG -->|Multi-doc Transactions| TX[Incident & Risk Scorer Transaction]

    IN -.->|Aggregated Metrics| ROL[telemetry_rollup Worker]
    ROL -->|Background 1-Min Bucket Writes| TSC[device_telemetry: Time-Series Collection]:::ts
    TSC -->|Analytical Queries Only| ANALYTICS[Historical Trends & SOC Charts]
```

* **`events` is a REGULAR Collection**:
  * Must support real-time Change Stream subscriptions so `detector.py` receives every event instantly through the oplog.
  * Must participate in multi-document transactions when correlating alerts and updating risk scores.
* **`device_telemetry` is a TIME-SERIES Collection**:
  * Used exclusively for minute-level metric rollups (`cpu`, `memory`, `temperature`, `eventCount`).
  * Yields a **3× storage compression ratio** (1.72 MiB vs 5.20 MiB for 200k docs) and a **15× smaller index footprint** (0.51 MiB vs 7.57 MiB).
  * Only queried for analytical dashboard graphs, never triggering detection alerts.

---

## 5. Per-Device Cryptographic Hash Chains

### Architecture

Rather than maintaining a single global blockchain (which would serialize all writes into a global lock), HoneyGraph implements an independent SHA-256 chain **per IoT device**:

$$\text{hash}_n = \text{SHA-256}(\text{hash}_{n-1} \parallel \text{canonical\_json}(\text{event}_n))$$

$$\text{hash}_0 = \text{"0"}^{64} \quad (\text{Genesis Hash})$$

```mermaid
graph LR
    subgraph Device 1 Chain
        D1E1[Event 1<br/>prevHash: 000...000<br/>hash: a1b2...] --> D1E2[Event 2<br/>prevHash: a1b2...<br/>hash: c3d4...] --> D1E3[Event 3<br/>prevHash: c3d4...<br/>hash: e5f6...]
    end
    subgraph Device 2 Chain (Parallel)
        D2E1[Event 1<br/>prevHash: 000...000<br/>hash: 1122...] --> D2E2[Event 2<br/>prevHash: 1122...<br/>hash: 3344...]
    end
```

### Concurrency Benefit
* Ingestion across 500+ devices runs with 100% parallelism without lock contention.
* Benchmark throughput reaches **19,592 events/s** with full hash verification.

### Limits & External Checkpointing
* **Linear Tamper Pinpointing:** If an attacker modifies or swaps an event at position $k$, the verifier recomputes hashes sequentially and pinpoints position $k$ as `modified` or `reordered`.
* **The Truncation Vulnerability (Tail Deletion):** If an adversary deletes the last $m$ events of a device chain, the remaining $1 \dots (n-m)$ events still form a mathematically valid chain! The chain links alone cannot prove that events were deleted from the tail.
* **The Solution (External Anchoring):** HoneyGraph periodically captures the state of all device heads, signs the snapshot, and anchors it externally in `checkpoints/YYYYMMDDHHMM.json` and `system_state`. When auditing, the verifier matches stored heads against the trusted external checkpoint anchor.

---

## 6. Rule Engine Safety Model

Detection rules are stored as JSON documents containing MongoDB aggregation pipelines. To prevent injection of arbitrary code or destructive operations by analysts or compromised accounts, HoneyGraph implements a strict multi-layer defense:

```mermaid
graph TD
    R[Rule Submission] --> AST[AST & Operator Validator]
    AST -->|Check 1: Read-Only Allowlist| AL{Allowed Operators?}
    AL -- No --> REJ1[HTTP 422: Disallowed Stage]
    AL -- Yes --> S2{Contains Forbidden Code?}
    S2 -- Yes --> REJ2[HTTP 422: Injection Blocked]
    S2 -- No --> RBAC{Caller Role == rule_admin?}
    RBAC -- No --> REJ3[HTTP 403: Forbidden]
    RBAC -- Yes --> DB[(Save to rules Collection)]
    DB --> CS[Change Stream Live Push]
```

### Safety Controls

1. **Strict Stage Allowlist**: Only read-only pipeline stages are allowed:
   `$match`, `$group`, `$project`, `$sort`, `$limit`, `$addFields`, `$count`, `$bucket`, `$unwind`.
2. **Explicit Blocklist**: Dangerous stages that mutate data, execute JavaScript, or span arbitrary collections are blocked:
   * **Write stages:** `$out`, `$merge`
   * **Arbitrary code execution:** `$function`, `$where`, `$accumulator`
   * **Unrestricted cross-collection joins:** `$lookup`
3. **Template Placeholders:** Rules use strict sanitized parameter substitution (`{{srcIp}}`, `{{deviceId}}`, `{{eventId}}`) to prevent pipeline injection.
4. **RBAC Isolation:** The operational API service (`api_svc`) possesses no write grants on `rules`. Rule mutations require the dedicated `rule_admin` MongoDB role.

---

## 7. Architectural Evaluation: MongoDB Native vs. Relational Stack

| Architectural Dimension | MongoDB Native (HoneyGraph) | Relational Equivalent (e.g. PostgreSQL + Extensions) | Trade-Off Analysis |
|---|---|---|---|
| **Polymorphic Event Payload** | Native BSON documents validated via JSON Schema `$jsonSchema`. | Requires `JSONB` column or multiple child tables with foreign keys. | MongoDB JSON Schema provides native schema-per-protocol validation without table explosion. |
| **Real-Time Detection Trigger** | Native Change Streams (`db.events.watch()`) tailing the oplog with resume tokens. | Requires `LISTEN/NOTIFY` triggers or external CDC (Debezium + Kafka). | PostgreSQL `LISTEN/NOTIFY` drops events if consumers disconnect; Kafka adds significant infrastructure complexity. |
| **Attack Chain Graph Traversal** | Native `$graphLookup` aggregation operator in single query. | Requires Recursive Common Table Expressions (`WITH RECURSIVE`). | Recursive CTEs can match `$graphLookup` for shallow graphs, but `$graphLookup` supports depth limiting, cycles, and breadcrumb projections natively. |
| **Time-Series Telemetry** | Built-in Time-Series Collections with automatic columnar compression. | Requires TimescaleDB extension (`hypertable`). | TimescaleDB hypertable is extremely mature; MongoDB native time-series requires no third-party binary plugins but lacks transactions/change streams. |
| **Geospatial Risk Clustering** | Native `2dsphere` indexes with `$geoWithin` / `$centerSphere`. | Requires PostGIS extension (`geometry` type and GiST index). | PostGIS is functionally superior for complex GIS analysis; MongoDB native 2dsphere is ideal and sufficient for spherical radius and coordinate querying. |
| **Operational Simplicity** | **Single unified cluster** providing documents, change streams, graphs, time-series, and geospatial natively. | **Requires 4–5 distinct plugins** (TimescaleDB + PostGIS + pg_graphql + Debezium) to match full feature set. | A relational system can theoretically cover all needs via plugins; MongoDB provides unified, out-of-the-box coverage with lower operational maintenance overhead. |
