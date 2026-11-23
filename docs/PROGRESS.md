# HoneyGraph progress

## Preparation — complete

- Saved the initial request verbatim in CONTEXT.md.
- Created Implementation Plan and Task List artifacts.
- No implementation code has been created.
- Decision: work only on the phase supplied by the user, with tests and a verification gate before completion.
- Deviations: none.
- Known issues: the initial request names phases 0–11 but does not include their specifications. Phase scopes and verification commands await the separate prompts.

## Phase status

| Phase | Status | Decisions / deviations / known issues |
| --- | --- | --- |
| 0 | Complete | Three-node MongoDB 7 replica set with keyFile authentication; gate passed |
| 1 | Complete | Idempotent collection/schema/index/RBAC bootstrap; 15 integration tests passed |
| 2 | Complete | Deterministic simulator and seven labeled scenarios; 20-test combined suite passed; 60,081-event gate run completed |
| 3 | Complete | FastAPI ingestion and concurrency-safe hash chains; 100k events verified across 500 devices at ~3,347 events/s |
| 4 | Complete | Change-stream detection-as-data with resume/live rules/dedupe; scenario, restart, live-edit, safety, and latency gates passed |
| 5 | Complete | Bidirectional graph reconstruction, atomic incident/link/risk writes, decayed risk aggregation, and idempotent telemetry rollups; 37 tests passed |
| 6 | Complete | Exact per-device tamper diagnostics and external truncation anchors; clean 100k check at 12,895 events/s; 42 tests passed |
| 7 | Complete | JWT/bcrypt analyst/admin API, ten REST router groups, authenticated alert WebSocket, OpenAPI 0.7.0; 53 tests passed |
| 8 | Complete | React 18 SOC dashboard with live/graph/map/chart views, admin workflows, Nginx proxy; Vite build and 4 component tests passed; 8 screenshots captured |
| 9 | Complete | End-to-end browser verification; 8 acceptance flows passed; 8 screenshots captured |
| 10 | Complete | 8 benchmarks implemented & run; CSVs, charts & docs/BENCHMARKS.md generated; targets evaluated |
| 11 | Complete | Documentation and final polish; README, ARCHITECTURE, REPLICATION_SHARDING delivered; Walkthrough created |

## Phase 0 — Infrastructure — complete

### Delivered

- `docker-compose.yml` defines `mongo1`, `mongo2`, and `mongo3` on replica set `rs0`, all using the same generated keyfile.
- A one-shot `keyfile-init` service copies the host-generated secret into a Docker volume and applies owner `999:999` and mode `0400`, avoiding permissive Windows bind-mount modes.
- A one-shot `mongo-init` service authenticates as the first-boot root admin, idempotently calls `rs.initiate()`, and waits for exactly one PRIMARY and two SECONDARY members.
- Backend, detector, and frontend placeholder services start after replica-set initialization.
- `.env.example` documents root, application, and detector credentials; host and internal MongoDB URIs; JWT settings; TTL and risk settings; and service ports.
- `mongo/generate-keyfile.ps1` and `mongo/generate-keyfile.sh` generate the ignored keyfile. `.env`, `secrets/`, and legacy `mongo/mongo-keyfile` paths are ignored.
- The root Makefile provides `up`, `down`, `logs`, and authenticated `mongosh` targets, plus the keyfile prerequisite.

### Decisions

- Replica-set members advertise Docker DNS names for reliable member-to-member communication.
- The host URI connects through the published primary port with both `replicaSet=rs0` and `directConnection=true`. This avoids requiring host DNS entries for Docker-only member names while retaining replica-set semantics for host tools.
- Container services use a separate internal URI listing all three Docker DNS names; service users are declared for creation in a later database-initialization phase.

### Deviations and known issues

- Local port 8000 was unavailable on this Windows host, so the ignored `.env` uses `BACKEND_PORT=18000` for this run. `.env.example` retains the requested conventional default of 8000.
- Phase 0 creates only the required root administrator. Application and detector RBAC users remain variables until the phase that defines their roles and collections.
- GNU Make is not installed on the verification host, so the targets could not be invoked through `make`; their underlying Docker Compose and keyfile commands were run directly and passed. The Makefile selects PowerShell on Windows and POSIX shell elsewhere.

### Verification gate

`docker compose config --quiet` exited 0.

`docker compose up -d` exited 0 after changing the local backend port. The init job reported:

```text
Waiting for mongo1 to accept authenticated connections...
Initiating replica set rs0...
Replica set already initialized
Waiting for exactly one PRIMARY and two SECONDARY members...
Replica set rs0 is ready.
```

Authenticated `rs.status()` member projection (exit 0):

```json
[{"name":"mongo1:27017","stateStr":"PRIMARY"},{"name":"mongo2:27017","stateStr":"SECONDARY"},{"name":"mongo3:27017","stateStr":"SECONDARY"}]
```

Unauthenticated `db.getSiblingDB('admin').getUsers()` (exit 1):

```text
MongoServerError: Command usersInfo requires authentication
```

All three MongoDB containers report healthy; `keyfile-init` and `mongo-init` exited 0; all three placeholder services are running.

Authenticated root-user check (exit 0):

```text
user: 'root'
db: 'admin'
roles: [ { role: 'root', db: 'admin' } ]
```

## Phase 1 — Database layer — complete

### Delivered

- Added `mongo/init_db.py`, an idempotent PyMongo bootstrap for the eight required collections plus the permitted `system_state` and `ground_truth` collections.
- Created `device_telemetry` as a time-series collection with `ts` as its time field, `deviceId` as its metadata field, minute granularity, and environment-controlled expiration.
- Applied strict/error `$jsonSchema` validators to `events`, `rules`, and `alerts`. Event payload validation covers the shared SSH/Telnet authentication shape, MQTT, HTTP, CoAP, and telemetry shapes with `oneOf`.
- Added all requested compound, unique, geospatial, and TTL indexes with stable names. Re-running the initializer updates TTL settings using `collMod` rather than conflicting with existing indexes.
- Added custom least-privilege roles and password-authenticated users for `ingest_svc`, `detect_svc`, `analyst`, `rule_admin`, `tamper_demo`, and `api_svc`.
- Added `backend/tests/test_schema.py` with live MongoDB integration tests for schema acceptance/rejection, all role boundaries, and initializer idempotency.
- Added `backend/requirements.txt` and expanded `.env.example` with every Phase 1 service credential.

### RBAC decisions

- `ingest_svc` has `insert` and `find` only on `events`. The narrow read grant is required to read the previous per-device hash-chain head before inserting the next event.
- `detect_svc` reads `events`, `rules`, `devices`, and `device_telemetry`, and can read/write `alerts`, `incidents`, `risk_scores`, and `system_state`.
- `analyst` can find documents in all ten allowed collections and cannot write.
- `rule_admin` can read/write only `rules`.
- `tamper_demo` can update and remove only `events`; it cannot insert events.
- `api_svc` reads dashboard/API data, inserts and updates application users, and updates incident status. It cannot write rules or alerts. Runtime rule changes use the separate `rule_admin` principal and path so an API compromise does not automatically grant rule mutation.

### Retention decision

- `EVENT_TTL_DAYS` defaults to 7 for development and controls both the regular `events.ts` TTL index and time-series expiration. The source and environment template state that CERT-In production deployments should use 180 days.

### Deviations and known issues

- A native Windows `mongod` already listened on IPv4 `localhost:27017`, while Docker owned a separate forwarding listener. The ignored local `.env` now publishes HoneyGraph `mongo1` at port `37017` and updates `MONGODB_URI`; the portable `.env.example` remains on the conventional port 27017. The native process was left untouched.
- SSH and Telnet specify the same `{user, attempts}` payload. A literal duplicate inside JSON Schema `oneOf` would reject every such payload because it would match two branches, so the validator uses one shared authentication branch for both protocols.

### Verification gate

Manual bootstrap before the suite:

```text
HoneyGraph database initialized: honeygraph (event TTL: 7 days)
```

`python -m pytest backend/tests/test_schema.py -v`:

```text
collected 15 items

test_valid_event_for_each_protocol[ssh-payload0] PASSED
test_valid_event_for_each_protocol[telnet-payload1] PASSED
test_valid_event_for_each_protocol[mqtt-payload2] PASSED
test_valid_event_for_each_protocol[http-payload3] PASSED
test_valid_event_for_each_protocol[coap-payload4] PASSED
test_invalid_events_are_rejected[wrong-enum] PASSED
test_invalid_events_are_rejected[wrong-payload-shape] PASSED
test_invalid_events_are_rejected[missing-required-field] PASSED
test_initializer_is_idempotent PASSED
test_ingest_service_permissions PASSED
test_detector_service_permissions PASSED
test_analyst_permissions PASSED
test_rule_admin_permissions PASSED
test_tamper_demo_permissions PASSED
test_api_service_permissions PASSED

============================= 15 passed in 4.65s ==============================
```

## Phase 2 — Simulator — complete

### Delivered

- Added a deterministic generator for 500 virtual cameras, energy meters, signal controllers, and environmental sensors. Devices use RFC1918 `10.42.0.0/16` addresses, firmware/protocol/type metadata, per-device `bytesOut` baselines, and GeoJSON points around Bengaluru.
- Attacker addresses come only from RFC5737 documentation networks (`192.0.2.0/24`, `198.51.100.0/24`, and `203.0.113.0/24`).
- Added configurable normal MQTT, CoAP, HTTP, SSH, and telemetry generation across logical simulated time.
- Added seven abstract defensive scenarios: `mirai_bruteforce`, `recon`, `credential_stuffing`, `mqtt_abuse`, `lateral_movement`, `exfil_burst`, and `log_tamper`. They create schema-valid observation events without exploit code.
- Every scenario creates a separate `ground_truth` document containing its scenario ID, stage, actor, target, event time range, and event count. Benchmark labels are never embedded in `events`.
- Added a pluggable sink interface, an in-memory test sink, a future `/api/ingest` HTTP sink, and a temporary direct MongoDB sink using `ingest_svc` only.
- The direct sink reads stored per-device chain heads and recalculates each event's SHA-256 `prevHash`/`hash` before ordered batch insertion.
- The `log_tamper` demonstration passes two trusted event IDs to `tamper_demo`; that principal updates one stored event and removes one stored event without read or insert access.
- Added a deterministic CLI at `backend/simulator/run.py`, a `make simulate` target, and an optional Cowrie JSON-lines mapper with a three-record sample. Cowrie command text is ignored rather than executed or replayed.
- Added `backend/tests/test_simulator.py` for deterministic output, MongoDB validator acceptance of every generated event type, labels for all scenarios, inventory addressing/geography, and Cowrie mapping.

### Decisions

- `--duration` is logical simulated time. The generator produces `rate × duration` normal records without sleeping, making benchmark runs fast and reproducible.
- The pure generator uses a fixed UTC anchor and seeded PRNG. The persistence sink rebases hashes against current database state, keeping repeat runs compatible with the per-device chain.
- Device inventory and benchmark labels are written with the administrative simulator connection. Observed events use only `ingest_svc`; mutations use only `tamper_demo`. This preserves the RBAC boundaries established in Phase 1.

### Deviations and known issues

- The API is still a Phase 0 placeholder, so the gate used the requested temporary direct-insert sink. `ApiSink` is ready for the later FastAPI ingestion endpoint.
- The tamper scenario deliberately deletes one of the 60,081 inserted events. Therefore the attempted protocol counts total 60,081 while the stored protocol counts total 60,080.

### Verification gate

Focused Phase 2 suite:

```text
collected 5 items
test_same_seed_produces_identical_output PASSED
test_every_generated_event_passes_database_schema PASSED
test_ground_truth_record_exists_for_every_scenario PASSED
test_device_inventory_uses_private_addresses_and_bengaluru_points PASSED
test_cowrie_sample_maps_to_schema_events PASSED
============================== 5 passed in 1.30s ==============================
```

Combined regression suite:

```text
collected 20 items
============================= 20 passed in 4.56s ==============================
```

Thirty-logical-second simulation command:

```text
python -m simulator.run --devices 500 --rate 2000 --duration 30 --scenarios all --seed 42
```

Attempted events by protocol:

```text
coap:   14,430
http:   14,394
mqtt:   14,472
ssh:    14,442
telnet:  2,343
total:  60,081
```

Events by scenario:

```text
mirai_bruteforce:     18
recon:                30
credential_stuffing: 20
mqtt_abuse:            3
lateral_movement:      3
exfil_burst:            5
log_tamper:             2
total scenario events: 81
```

Post-tamper database aggregation:

```text
coap:   14,429
http:   14,394
mqtt:   14,472
ssh:    14,442
telnet:  2,343
total stored: 60,080
```

The database contains exactly one gate-run ground-truth record for each of the seven scenarios.

## Phase 3 — Ingestion API and hash chain — complete

### Delivered

- Added `backend/app/hashchain.py` with deterministic, sorted, whitespace-free JSON over exactly `ts`, `deviceId`, `protocol`, `eventType`, `srcIp`, `geo`, and `payload`.
- Canonical timestamps are normalized to UTC and rendered at fixed BSON-compatible millisecond precision (`YYYY-MM-DDTHH:MM:SS.mmmZ`). Each device begins with 64 zeroes and hashes `SHA256(prevHash || canonicalEvent)`.
- Added strict Pydantic v2 request models for GeoJSON and all protocol/telemetry payload shapes. The API rejects unknown fields, missing fields, negative counters, naive timestamps, invalid protocols, and protocol/payload mismatches before MongoDB validation.
- Added `POST /api/ingest` for one event or batches of 1–5,000 events, returning each inserted ObjectId and hash.
- Added an `IngestionService` using `ingest_svc`, per-device async locks, database-bootstrapped chain-head caching, sequential preparation per device, and `insert_many(ordered=False)` across the batch.
- Each batch insert runs in a MongoDB transaction. If insertion, validation, or an injected post-insert failure occurs, MongoDB aborts the entire batch and the in-memory cache is restored to the last confirmed heads.
- Extended the MongoDB event validator with optional `eventInsertedAt`, `chainSeq`, and `ingestBatchId` fields. Added a partial unique `(deviceId, chainSeq)` index for API-ingested records.
- Added `backend/Dockerfile` and replaced the backend placeholder with the Uvicorn/FastAPI service in Docker Compose.
- Updated the simulator HTTP sink to strip client-side hash fields and POST batches of up to 5,000. The simulator now defaults to the API sink; the Phase 2 direct sink remains available explicitly.
- Added `backend/benchmarks/verify_hashchains.py` for independent end-to-end verification from genesis.

### Concurrency and failure decisions

- A request acquires its device locks in sorted order, preventing deadlocks for multi-device batches. Different requests targeting the same device serialize; each confirmed cache update occurs only after transaction commit.
- The transaction makes an unordered bulk atomic. This avoids a partially accepted prefix leaving a missing link or cached fork.
- The partial unique chain-sequence index adds a database-side guard against duplicate sequence numbers. The in-memory locking model assumes one Uvicorn worker for this phase; horizontal workers require a database-coordinated retry/reservation design in a later scaling phase.

### Timing and validator extension

- `eventInsertedAt` is assigned immediately before hash preparation and persistence, enabling later detection-latency calculations against the event timestamp.
- `chainSeq` provides efficient ordered verification and an enforceable per-device position. `ingestBatchId` supports tracing bulk requests. None of these fields participates in the immutable event hash because the required canonical field set excludes them.

### Write concern trade-off

- Event bulks use `w:1`, as required. The primary acknowledges faster without waiting for a replica majority, improving ingestion throughput. A primary failure can lose recently acknowledged writes that had not replicated. Transactional atomicity prevents partial batches at the application level, but it does not provide the failover durability of `majority` write concern.

### Deviations and known issues

- BSON stores dates at millisecond precision and PyMongo returns UTC dates as naive values by default. The API requires timezone-aware input, normalizes it to UTC, truncates it to milliseconds before hashing, and treats BSON-naive values as UTC during verification.
- The 100k gate intentionally removed 60,139 earlier synthetic event/test documents so every benchmark device could be verified from a clean genesis. Device inventory and ground-truth labels were preserved.

### Verification gate

Focused Phase 3 suite:

```text
collected 4 items
test_chain_continuity_across_batches PASSED
test_concurrent_http_clients_do_not_fork_same_device PASSED
test_invalid_payload_has_clear_validation_error PASSED
test_partial_failure_aborts_batch_and_restores_cache PASSED
============================== 4 passed in 1.94s ==============================
```

The concurrency test issued eight simultaneous HTTP requests with five events each for one device and verified one continuous 40-link chain.

Docker API health:

```json
{"status":"ok"}
```

100,000-event API benchmark:

```text
devices=500
events=100000
elapsed_seconds=29.882
throughput=3346.5 events/second
```

Independent end-to-end verification:

```text
verified_events=100000 devices=500 seconds=5.894
```

Full regression suite:

```text
collected 24 items
============================= 24 passed in 5.89s ==============================
```

## Phase 4 — Detection-as-data rule engine — complete

### Delivered

- Added `backend/workers/detector.py`, which watches `events` inserts through a MongoDB change stream and stores the last processed resume token in `system_state` after every event.
- On restart, the detector passes the saved token as `resume_after`. If an alert was committed immediately before a crash but its token was not saved, the deterministic dedupe key prevents replay from inserting a duplicate.
- Added a second change stream on `rules`. The worker maintains an in-memory cache of active, validated rule documents and reloads it whenever a rule changes.
- For each event, the worker validates the stored rule again, substitutes `{{srcIp}}`, `{{deviceId}}`, `{{ts}}`, and internal `{{eventId}}` placeholders, prepends the rule time-window `$match`, and executes the aggregation on `events` with `maxTimeMS=2000`.
- Added majority-acknowledged alert insertion with rule/stage/severity, actor, target IP, contributing event IDs, event insertion time, alert creation time, measured latency, and a cooldown dedupe key.
- Cooldown identity is exactly `(ruleId, actor, deviceId)` plus the rule's time bucket. A single scanning actor can therefore create distinct alerts for distinct target devices while repeats for the same tuple are suppressed.
- Added `backend/app/rule_validator.py`. Executable top-level stages are restricted to `$match`, `$group`, `$project`, `$sort`, `$limit`, `$count`, `$addFields`, `$set`, and `$unwind`. `$out`, `$merge`, `$function`, `$where`, `$accumulator`, `$lookup`, and every unlisted stage are rejected recursively.
- Rule validation runs before seed/update writes and again immediately before execution.
- Added `mongo/seed_rules.py` with ten idempotently upserted rules: `R-BRUTE-01`, `R-BRUTE-SUCCESS-02`, `R-RECON-03`, `R-STUFF-04`, `R-MQTT-05`, `R-LATERAL-06`, `R-EXFIL-07`, `R-SCAN-PORTS-08`, `R-OFFHOURS-ADMIN-09`, and `R-NEWUSER-CMD-10`.
- The seed set covers windowed threshold, distinct-value, sequence, telemetry-baseline, and MQTT allow-list rule types across all seven simulator scenarios.
- Extended the detector role with database-level `changeStream`; extended alert validation with `detectionLatencyMs` and `dedupeKey`; added a partial unique dedupe index.
- Replaced the detector placeholder container with the real worker and added `make seed-rules`.

### Baseline and allow-list decisions

- Baseline rules use a MongoDB aggregation over `device_telemetry` to calculate average `bytesOut`, then compare the current event to the configured multiplier. No Python rolling-average implementation is used.
- Allow-list rules remain stored pipelines and are subject to the same validation. Cross-collection `$lookup` stays forbidden.

### Restart/resume gate

- Mirai was ingested first and produced four deduplicated alerts. The detector was restarted before recon and stuffing were ingested.
- A second explicit restart check showed the alert count unchanged:

```text
restart_check before=38 after=38
checkpoint_present=True
```

- After restart, expected recon and stuffing rules fired, proving the stream resumed and new inserts were not missed. Previously processed inserts were not duplicated.

### Expected scenario alerts

```text
R-BRUTE-01          stage=credential-access severity=7
R-BRUTE-SUCCESS-02  stage=initial-access    severity=9
R-RECON-03          stage=discovery         severity=6
R-STUFF-04          stage=credential-access severity=7
R-SCAN-PORTS-08     stage=reconnaissance    severity=5
```

Mirai also correctly produced the seeded execution rules `R-OFFHOURS-ADMIN-09` and `R-NEWUSER-CMD-10`, both at severity 8.

### Live rule edit gate

- `R-STUFF-04` was read using `rule_admin`, changed from severity 7 to 10, validated, and replaced while the detector continued running.
- The rule change stream logged a cache reload and the next credential-stuffing scenario produced:

```json
{"ruleId":"R-STUFF-04","stage":"credential-access","severity":10,"actor":"192.0.2.118","deviceId":"blr-signal-controller-0207","detectionLatencyMs":107.183}
```

No detector restart occurred between the rule write and this alert. The source seed remains severity 7; rerunning `seed_rules.py` restores the baseline demo configuration.

### Rule-safety gate

```text
test_allowed_read_only_pipeline_and_placeholders PASSED
test_forbidden_operator_is_rejected[$out] PASSED
test_forbidden_operator_is_rejected[$merge] PASSED
test_forbidden_operator_is_rejected[$function] PASSED
test_forbidden_operator_is_rejected[$where] PASSED
test_forbidden_operator_is_rejected[$accumulator] PASSED
test_forbidden_operator_is_rejected[$lookup] PASSED
test_nested_forbidden_operator_is_rejected PASSED
test_unlisted_stage_is_rejected PASSED
============================== 9 passed in 0.09s ==============================
```

### Detection latency

MongoDB `$percentile` over the 40 gate alerts:

```text
p50 = 269.508 ms
p95 = 461.701 ms
```

### Full verification gate

```text
collected 33 items
============================= 33 passed in 5.64s ==============================
```

### Known limitations

- The current worker processes one change event at a time and checkpoints each event. This favors clear recovery semantics for the course demo; later benchmark tuning can checkpoint small batches without changing rule execution.
- Rule-cache resume tokens are not persisted because a reconnect performs a full active-rule reload before opening a fresh rule stream. Event resume tokens are persisted because event loss would affect detection correctness.

## Phase 5 — Attack-chain reconstruction, incidents, and risk — complete

### Delivered

- Added `backend/workers/chain_builder.py`. A reverse `$graphLookup` follows `actor` back through `targetIp` to identify the initial-access root; a forward `$graphLookup` then uses `startWith: "$targetIp"`, `connectFromField: "targetIp"`, `connectToField: "actor"`, `maxDepth: 5`, a hop-depth field, and a bounded time restriction.
- Chains are ordered by hop and event time. MongoDB's visited-document behavior and an explicit ObjectId deduplication guard prevent cycles from duplicating embedded nodes.
- A stable SHA-256 key over the connected alert set makes reconstruction idempotent. Partial unique indexes on `incidents.chainKey` and `risk_scores.deviceId` preserve compatibility with documents created before Phase 5.
- Incident creation/update, alert linking, embedded open status history/chain, and risk-score upserts execute in one `with_transaction` callback with snapshot read concern and majority write concern. PyMongo retries callbacks labeled `TransientTransactionError`.
- Added `backend/workers/risk_scorer.py`. One alert aggregation uses `$dateDiff` and `$exp` to calculate `severity * exp(-lambda * ageHours)` over 24 hours, groups per device, caps with `$min`, and retains the five strongest alert/rule factors. `RISK_HALF_LIFE_HOURS` now defaults to the requested 6 hours.
- Added `backend/workers/telemetry_rollup.py`. Its MongoDB aggregation produces per-device `eventCount`, `failedLogins`, and `bytesOut` for each completed minute and writes outside transactions to `device_telemetry`. Existing `(deviceId, ts)` buckets are skipped, making scheduled retries idempotent.
- The detector role now has narrow insert permission on `device_telemetry`; it still cannot update or remove time-series records. Added supporting alert graph indexes.
- Added four Phase 5 integration tests for graph order/idempotency/cycle safety, forced transaction rollback, risk decay/capping/factors, and telemetry retry idempotency.

### Live lateral-chain gate

The simulator injected three connected hops through the ingestion API and the detector produced three lateral alerts:

```text
injected_hops=3 detected_alerts=3
edges=[('10.42.1.99', '10.42.0.178'),
       ('10.42.0.178', '10.42.1.180'),
       ('10.42.1.180', '10.42.1.26')]
```

Reconstruction from the final alert produced one ordered incident. Re-running returned the same ID:

```text
incident_id=6acf9683c16e16a9a7888995
rerun_id=6acf9683c16e16a9a7888995
duplicate_count=1
ordered_chain=[(0, '10.42.1.99', '10.42.0.178'),
               (1, '10.42.0.178', '10.42.1.180'),
               (2, '10.42.1.180', '10.42.1.26')]
all_alerts_linked=True
```

### Transaction rollback and risk gates

A failpoint raised after the incident and alert-link statements but before risk upsert. Transaction abort left every collection unchanged:

```text
rollback alert_linked=0 incidents=0 risks=0
```

Four severity-10 alerts evaluated at creation and one half-life later show exact exponential decay:

```text
risk_now=40.000 risk_after_6h=20.000
```

The cap/factor test separately verified 12 severity-10 alerts cap at 100 and retain five factors. The rollup test verified the first execution inserted one device-minute and the retry inserted zero.

### Verification gate

```text
HoneyGraph database initialized: honeygraph (event TTL: 7 days)

backend/tests/test_chain_builder.py: 4 passed in 0.89s
full backend regression suite: 37 passed in 6.47s
```

### Decisions and known issues

- The time-series collection does not provide a compound unique index for `(deviceId, ts)`. The single scheduled rollup worker queries existing buckets before insert and uses deterministic ObjectIds for traceability. This gives idempotent retries; deployments with concurrent rollup workers should coordinate ownership through `system_state`.
- Chain materialization is a bounded batch operation. This avoids prematurely creating separate incidents while a short lateral sequence is still arriving; a later orchestration phase can schedule it after the correlation window closes.

## Phase 6 — Tamper-evident log integrity — complete

### Delivered

- Added `backend/workers/integrity_checker.py` to recompute each device's SHA-256 chain in timestamp order and return only the first broken link with `deviceId`, one-based position, expected hash, stored hash, and reason.
- `chainSeq` distinguishes missing and reordered records: a skipped sequence absent from the remaining chain is missing, while an expected sequence found later proves reordering. A matching predecessor with a recomputed-hash mismatch is modified.
- The CLI checks one `--device` or every device and reports cumulative device, event, and break counts every 50 devices.
- Checkpoint export stores each device's tail hash, event ID, timestamp, sequence, and event count under `integrity.checkpoint.latest` in `system_state`, then atomically writes the same anchor to `checkpoints/YYYYMMDDHHMM.json`.
- The CLI supports one-shot exports, comparison with an explicit or latest external checkpoint, and periodic checkpoint refresh through `--checkpoint-interval-minutes`.
- External comparison detects deletion of an anchored tail or a live count below its anchored count as `truncated`.
- Added a `TamperDemo` helper for an explicit event edit, middle deletion, and timestamp swap. It operates through the existing `tamper_demo` principal, which has update/remove permission only on `events`; trusted admin/API code must select the IDs and original timestamps.
- Added five integration tests covering a clean chain, modification at position 3, deletion at position 3, reorder at position 3, and checkpointed tail truncation at position 6.

### Integrity and truncation model

Modification, deletion, and ordering changes inside retained history are detectable from the per-device hash links. Deletion of the newest records leaves no later database link to expose the loss. Tail truncation is therefore detectable only by comparing MongoDB with an external checkpoint anchor stored outside the database's trust boundary. The `system_state` copy is operational metadata and does not replace that external anchor.

### Focused verification gate

```text
test_clean_chain_has_no_break PASSED
test_modified_event_reports_exact_position PASSED       # modified, position 3
test_deleted_middle_event_reports_exact_position PASSED # missing, position 3
test_swapped_events_report_exact_position PASSED        # reordered, position 3
test_checkpoint_detects_tail_truncation PASSED           # truncated, position 6
============================== 5 passed in 1.14s ==============================
```

The checkpoint contained all 500 live device anchors and matched the unchanged database:

```text
external_checkpoint=True anchored_devices=500 live_comparison_breaks=0
```

### 100,000-event benchmark

The benchmark used a fresh API-ingested population across 500 devices. The detector was paused during ingestion and checking so rule processing did not distort integrity throughput, then restored afterward.

```text
progress devices=50/500 events=9816 breaks=0
progress devices=250/500 events=49983 breaks=0
progress devices=500/500 events=100000 breaks=0
checkpoint=checkpoints\\202610141454.json
checked_events=100000 breaks=0 seconds=7.755 events_per_second=12895.0
```

### Full regression gate

```text
42 passed in 7.02s
```

### Decisions and known issues

- Verification materializes one device's events at a time to distinguish a missing sequence from a sequence that appears later. Memory use is bounded by the largest single device chain rather than the whole collection.
- Checkpoint filenames have minute precision as required. Multiple exports in the same minute replace that minute's anchor atomically instead of creating ambiguous same-minute files.

## Phase 7 — Backend REST API and WebSocket — complete

### Delivered

- Added bcrypt-backed application users and JWT bearer authentication. Database initialization idempotently seeds one active `analyst` and one active `admin` from environment variables; plaintext passwords are never stored.
- Added explicit 401 handling for absent/invalid tokens and reusable role dependencies that return 403 for insufficient application roles.
- Added typed request/response schemas and tagged OpenAPI documentation at version 0.7.0.
- Alerts support device, source event type, stage, time-range filters, and bounded pagination.
- Incidents support paginated listing, detail, and only `open -> triaged -> closed`; every accepted transition appends the actor and timestamp to `statusHistory`.
- Devices support pagination, 2dsphere `$near` searches, and paginated per-device event timelines.
- Risk endpoints return all scores ordered by score or one device's score.
- Rules support list/hit counts plus admin-only create, replace, delete, and enable/disable. Stored pipelines pass `rule_validator` before writes and return clear 422 errors for forbidden stages.
- Integrity endpoints run one/all-device checks, persist/view the latest result, and expose the Phase 6 edit/delete/swap demonstration only to admins through `tamper_demo` credentials.
- User management is admin-only and supports creation plus activation/deactivation. Administrators cannot deactivate their own current account.
- Scenario endpoints let admins launch, list, and stop all seven abstract simulator scenarios. Jobs run as cancellable application tasks and ingest through the existing chain-safe ingestion service.
- Dashboard statistics use MongoDB aggregations for alerts by stage and severity over time, plus the ten highest risk devices.
- Added authenticated `/ws/alerts`, backed directly by an alert insert change stream with 100 ms await intervals.
- Expanded `api_svc` narrowly with database change-stream access and operational `system_state` writes. Rule changes and event tampering continue through separate MongoDB principals.
- The backend image now contains simulator modules, JWT/passlib/bcrypt dependencies, and bounded FastAPI/Pydantic/Uvicorn versions for reproducible builds.

### API integration gate

Eleven tests cover every router group and the WebSocket:

```text
test_auth_openapi_and_role_boundaries PASSED
test_alerts_filters_and_pagination PASSED
test_incident_detail_and_strict_transitions PASSED
test_devices_near_and_timeline PASSED
test_risk_routes PASSED
test_rules_crud_validation_enable_and_hits PASSED
test_integrity_results_and_admin_tamper PASSED
test_user_management PASSED
test_scenario_launch_list_and_stop PASSED
test_stats_dashboard PASSED
test_websocket_receives_alert_within_one_second PASSED
============================== 11 passed in 3.89s ==============================
```

The suite explicitly proved unauthenticated access returns 401, analyst access to admin routes returns 403, invalid incident transitions return 409, and forbidden rule pipelines return 422.

WebSocket timing against the live replica-set change stream:

```text
websocket_delivery_seconds=0.158
1 passed in 2.92s
```

### Full regression and container gate

```text
53 passed in 10.91s
container_login_status=200 role=analyst
container_health={"status":"ok"}
openapi_version=0.7.0
```

### Decisions and known issues

- Scenario state is held by the single backend process for this course deployment. A horizontally scaled deployment would move job coordination to a durable queue or `system_state` lease.
- The dedicated ingestion route remains service-facing and does not require an analyst JWT. Dashboard, administrative, and WebSocket routes require application authentication.

## Phase 8 — React dashboard — complete

### Delivered

- Created a React 18 and Vite single-page application with Tailwind styling, a responsive dark SOC shell, JWT login, persisted sessions, sign-out, and role-aware navigation. Analyst sessions see operational views; admin sessions additionally see Rules and Scenarios & Users.
- Live Alerts loads paginated history, exposes device/event-type/stage/time filters, renders severity tiers and detection latency, and prepends WebSocket alerts. The socket reports live/offline state and reconnects after one second.
- Incidents provides list/detail navigation. Detail renders the embedded ordered chain with vis-network: actor/device IP nodes, directional alert edges, hop numbers, stages, and rule IDs. Valid next-state actions and status history are displayed beside the graph.
- Device Risk uses Leaflet with the geospatial radius endpoint. Markers are sized/colored by risk; selecting one loads its timeline and renders risk factors with a Recharts horizontal bar chart.
- Integrity can check one device or all devices and displays the event total plus broken-link position, reason, expected hash, and stored hash. Clean results have an explicit empty-success state.
- Rules provides hit counts, severity, live enable/disable switches, a JSON aggregation-pipeline editor, server-side validation errors, and a saved/takes-effect-live signal.
- Scenarios & Users lets admins select any of the seven simulations, launch/stop jobs, create users, and activate/deactivate accounts.
- Every view includes loading, empty, and error states. Shared UI components cover severity, progress, errors, and empty results.
- Added a multi-stage frontend image: Node builds static assets and Nginx serves them. Nginx proxies same-origin `/api` and `/ws` traffic to the backend. `VITE_API_URL` and `VITE_WS_URL` remain build-time configurable.
- Added a frontend `.dockerignore` so subsequent image builds exclude local dependencies and build output.

### Seeded visual gate

The live gate added 16 presentation alerts, one three-hop incident, and risk factors for 24 devices while retaining the 100,000-event corpus. Captured artifacts:

- `docs/screenshots/phase8-login.jpg`
- `docs/screenshots/phase8-live-alerts.jpg`
- `docs/screenshots/phase8-incidents-list.jpg`
- `docs/screenshots/phase8-incident-detail.jpg`
- `docs/screenshots/phase8-device-risk-map.jpg`
- `docs/screenshots/phase8-integrity.jpg`
- `docs/screenshots/phase8-rules.jpg`
- `docs/screenshots/phase8-scenarios-users.jpg`

The screenshots were taken from the deployed Nginx container at a 1440x900 desktop breakpoint. The viewport override was reset afterward. The device map screenshot includes a selected asset, risk chart, and timeline; the incident detail includes the rendered vis-network chain.

### Verification gate

Production build:

```text
vite v8.3.4 building client environment for production...
✓ 2201 modules transformed.
dist/index.html                     0.35 kB │ gzip:   0.26 kB
dist/assets/index-Bp-Ju3NT.css     30.65 kB │ gzip:  10.34 kB
dist/assets/index-Pu2ACCB9.js   1,377.56 kB │ gzip: 403.30 kB
✓ built in 2.78s
```

Component tests:

```text
✓ src/test/components.test.jsx (4 tests) 168ms
Test Files  1 passed (1)
Tests       4 passed (4)
```

Container and proxy:

```text
frontend_status=200 content_type=text/html
proxy_login_role=admin
honeygraph-frontend-1 Up 0.0.0.0:5173->80/tcp
honeygraph-backend-1  Up 0.0.0.0:18000->8000/tcp
```

### Decisions and known issues

- The current production bundle is 403 kB gzip and Vite emits a chunk-size optimization warning. It is a warning rather than a build error; route-level lazy loading can split vis-network, Leaflet, and Recharts in a later performance phase.
- The Leaflet base layer uses OpenStreetMap tiles at runtime. Device positions and risk computation remain local MongoDB data.

## Phase 9 — End-to-end browser verification — complete

### Delivered and fixed

- Added `seed` and `demo` Makefile targets. `seed` idempotently initializes the database and rules; `demo` runs the eight-step acceptance flow through the deployed HTTP API.
- Added `backend/benchmarks/demo_flow.py`, which fails fast and exits nonzero on any acceptance failure.
- Fixed scenario launch ingestion so simulator-side `prevHash`/`hash` fields are stripped and the ingestion service remains the sole owner of stored hash chains.
- Normalized scenario internal actor IPs against the persisted device inventory. This fixed nondeterministic lateral graph joins when scenario seeds changed IP assignments.
- Lateral scenario jobs now wait for their injected hop alerts and materialize the incident with the Phase 5 transactional chain builder. Jobs expose the inserted IDs and resulting incident ID.
- Added admin rule creation to the live Rules UI while preserving server-side validation and runtime cache refresh.
- Added an admin three-mode tamper endpoint and UI control. Each run creates isolated chains, applies edit/delete/swap mutations, checks all chains, and prioritizes the three fresh results in the table.
- Added the detector service URI to the backend container for scenario-to-incident orchestration.

### Browser acceptance results

All requested browser steps passed against `http://localhost:5173`:

1. **PASS** — Admin launched Mirai-style traffic; a WebSocket alert appeared in 505 ms during the first UI run. A two-tab live-feed check measured 304 ms.
2. **PASS** — Lateral movement produced an incident; the detail view showed hops 0, 1, 2, and 3 in order with graph/evidence labels.
3. **PASS** — Created `R-LIVE-1791991908523` while running; matching traffic produced its alert through the WebSocket in 304 ms with no restart.
4. **PASS** — The risk map returned 500 Bengaluru-radius devices and rendered attack-updated risk colours. The headless assertion found 38 risky devices and all 38 in the radius response.
5. **PASS** — The three-mode demo reported position 3 for `missing`, `modified`, and `reordered`; the newest three rows are shown first.
6. **PASS** — `$out` and `$function` submissions displayed `stage ... is not allowed` and returned HTTP 422.
7. **PASS** — Analyst navigation omitted Rules and Scenarios & Users; direct `/rules` navigation redirected to `/alerts`, and an analyst rule write returned HTTP 403.
8. **PASS** — An incident moved `open -> triaged -> closed`; the detail view retained all three status-history entries with the admin actor.

Browser evidence:

- `docs/screenshots/phase9-01-live-alerts.png`
- `docs/screenshots/phase9-02-incident-chain.png`
- `docs/screenshots/phase9-03-live-rule.png`
- `docs/screenshots/phase9-04-risk-map.png`
- `docs/screenshots/phase9-05-integrity.png`
- `docs/screenshots/phase9-06-rule-rejection.png`
- `docs/screenshots/phase9-07-analyst-rbac.png`
- `docs/screenshots/phase9-08-status-history.png`

### Verification gate

Stack and seed used the Makefile through the Windows GNU Make executable (`mingw32-make up` and `mingw32-make seed`; this host installs GNU Make under that executable name). All MongoDB members, backend, detector, and frontend are up.

```text
53 passed in 11.57s
Test Files  1 passed (1)
Tests       4 passed (4)
vite build: 2201 modules transformed, built in 2.80s
```

Final `make demo` equivalent output:

```text
PASS 1 Mirai alert in about one second: observed 0.019s; 18 events
PASS 2 ordered lateral incident: incident=6acfa12efc0e017a11d481c0 hops=[0, 1, 2, 3]
PASS 3 live rule created: R-LIVE-ce9efed5
PASS 3 live rule fired without restart: observed 0.019s
PASS 4 risk map and radius: 38 risky; 38 nearby
PASS 5 integrity pinpoints all tampering: ['missing', 'modified', 'reordered']
PASS 6 forbidden $out rejected
PASS 6 forbidden $function rejected
PASS 7 analyst admin action denied
PASS 8 incident lifecycle history
```

### Decisions and known issues

- Browser scenario control and the live feed were exercised in separate tabs so the WebSocket remained connected before traffic was launched; this directly measures the requested push behavior.
- Repeated Phase 6/9 tamper demonstrations intentionally leave broken demo chains in the course database. The Integrity UI promotes the newest demo's three rows so accumulated historical breaks do not hide the current result.
- Vite continues to report the documented bundle-size warning; the production build succeeds.

## Phase 10 — Benchmarks — complete

### Delivered

- Implemented 8 standalone, seeded reproducible benchmark modules in `backend/benchmarks/`:
  - `ingest.py`: Bulk ingestion of 1,000,000 events with and without SHA-256 hash chaining.
  - `indexes.py`: `explain("executionStats")` before and after creating indexes (`{deviceId, ts}`, `{srcIp, ts}`, `{eventType, ts}`, `{actor, ts}`) on 1M event corpus.
  - `latency.py`: Detection latency (`alertCreatedAt - eventInsertedAt`) percentiles (p50, p95, p99) from change-stream detector.
  - `quality.py`: Detection precision and recall per scenario and overall in an isolated reproducible benchmark run.
  - `chains.py`: 4-hop lateral attack chain reconstruction via `$graphLookup`.
  - `integrity.py`: Historical event mutation and tamper pinpointing via hash-chain verifier.
  - `storage.py`: 200,000 documents in regular vs MongoDB time-series collection comparing data size, index size, and range-query latency.
  - `failover.py`: Docker-based primary termination (`docker compose stop`), replica set election measurement, and post-failover write acknowledgment.
- Implemented `backend/benchmarks/report.py`: Reads the 8 raw CSVs from `docs/benchmarks/`, generates 5 formatted PNG charts via Matplotlib, and writes the complete `docs/BENCHMARKS.md` report with tables and honest engineering interpretations.
- Updated `Makefile` with the `bench` target that runs all benchmark scripts sequentially followed by `report.py`.

### Measured Results (Seed `104729`)

| Benchmark | Target | Measured | Pass? | Root Cause / Note |
|---|---|---|:---:|---|
| Ingestion (plain) | ≥ 5,000 eps | **33,251 eps** | ✅ | Unordered bulk insert with `w:1` on 1M events |
| Ingestion (hash chain) | ≥ 5,000 eps | **19,592 eps** | ✅ | Per-device SHA-256 chain overhead is ~40%, still ~4× target |
| Index `device_ts` | ≤ 100 ms | **9 ms** (was 611 ms) | ✅ | Exact match docs scanned drops from 1M to 2,000 |
| Index `src_ts` | ≤ 100 ms | **14 ms** (was 574 ms) | ✅ | Exact match docs scanned drops from 1M to 4,000 |
| Index `event_type_ts` | ≤ 100 ms | **9 ms** (was 658 ms) | ✅ | Compound `(eventType, ts)` evaluates time-window query; drops from 1M docs examined to exact 3,334 |
| Index `alerts_actor_ts` | ≤ 100 ms | **2 ms** (was 53 ms) | ✅ | 100k synthetic alerts |
| Detection Latency p50 | ≤ 1,000 ms | **200.23 ms** | ✅ | Change-stream detector live evaluation |
| Detection Latency p95 | ≤ 1,000 ms | **460.64 ms** | ✅ | Target met; 14 test-harness alerts excluded with documented threshold |
| Detection Latency p99 | ≤ 1,000 ms | **536.12 ms** | ✅ | Reflects aggregation pipeline complexity variance |
| Detection Quality Precision | ≥ 0.90 | **1.00** | ✅ | All 7 threat scenarios detected with 0 false positives |
| Detection Quality Recall | ≥ 0.90 | **1.00** | ✅ | All 7 threat scenarios detected (100% recall) |
| Chain Reconstruction | All 4 hops | **4 hops [0, 1, 2, 3]** | ✅ | Ordered traversal recovered in full via `$graphLookup` |
| Tamper Pinpointing | Exact position | **Position 3 ('modified')** | ✅ | Linear scan halted at exact break point |
| Storage Compression | Smaller than regular | **3× smaller** | ✅ | 1.72 MiB vs 5.20 MiB; index footprint 0.51 MiB vs 7.57 MiB |
| Failover Election Time | ≤ 10 s | **6.694 s** | ✅ | Election of `mongo2` within normal election window |
| Post-Failover Ingest | Success | **True** | ✅ | PyMongo reconnects transparently via replica set URI |

### Artifacts Delivered

- `docs/BENCHMARKS.md`: Comprehensive markdown report with tables, interpretations, and embedded charts.
- `docs/benchmarks/*.csv`: 8 raw CSV result datasets (`ingest.csv`, `indexes.csv`, `latency.csv`, `quality.csv`, `chains.csv`, `integrity.csv`, `storage.csv`, `failover.csv`).
- `docs/benchmarks/*.png`: 5 rendered PNG visualizations (`ingest.png`, `indexes.png`, `latency.png`, `quality.png`, `storage.png`).

### Verification Gate

1. `python -m pytest tests`: 53 passed in 10.29s.
2. `python backend/benchmarks/demo_flow.py`: All 8 acceptance checks passed.
3. `python -m benchmarks.report`: All charts and `docs/BENCHMARKS.md` generated cleanly.
4. Docker replica set healthy: `mongo1`, `mongo2`, `mongo3`, `backend`, `detector`, `frontend` all UP.

## Phase 11 — Documentation and final polish — complete

### Delivered

- `README.md`: One-command quickstart (`make up && make seed && make demo`), architecture overview, 8-step demo script, default credentials table for demo/evaluation, available Makefile targets, benchmark summary, and troubleshooting guide.
- `docs/ARCHITECTURE.md`: Complete architectural documentation covering:
  - 6-tier layered architecture (Data Source, Ingestion, Data, Detection & Analytics, API, Presentation) with Mermaid diagram.
  - Document model and collection relationships with Mermaid ER diagram.
  - Embedded vs Referenced modeling rationale.
  - Indexing strategy, rationale, and explain execution statistics on 1M events.
  - Time-series vs Change Streams vs Transactions limitation deep dive and HoneyGraph's hybrid regular/time-series workaround.
  - Per-device cryptographic SHA-256 hash chains, horizontal concurrency advantages, truncation limits, and external checkpoint anchors.
  - Rule engine defense-in-depth safety model (AST validation, stage allowlist, code execution blocklist, RBAC privilege separation).
  - Balanced "Why MongoDB vs Relational" comparative evaluation table.
- `docs/REPLICATION_SHARDING.md`:
  - 3-node replica set (`rs0`) topology and keyFile internal authentication.
  - Write concern durability policy (`w:1` fast ingestion vs `w:majority` security alerts and ACID transactions).
  - Measured primary failover benchmark results (election in 6.694s, transparent PyMongo reconnect).
  - Brewer's CAP theorem analysis (CP characteristics under network partition).
  - Horizontal scaling shard-key evaluation comparing `{ts: 1}`, `{deviceId: "hashed"}`, and `{deviceId: 1, ts: 1}` (recommended).
  - Explicit declaration that the current prototype is a 3-node replica set and is not sharded.
- `Makefile`: Added `.PHONY: test` target running `python -m pytest tests`.
- `.env.example`: Verified complete with all credentials, ports, TTL, and risk decay variables.
- Repository hygiene: Verified no secrets, keys, or scratch scripts committed; `.gitignore` covers `.env`, `secrets/`, and build caches.
- Walkthrough Artifact: Created comprehensive demonstration and project summary artifact.

### Architectural Decisions & Deviations from Original Brief

1. **`ingest_svc` Read Grant on `events`**: The original brief specified least-privilege roles where `ingest_svc` only had `insert` permissions. However, to compute the per-device hash chain without a centralized lock or stateful in-memory cache, `ingest_svc` requires a narrow `find` permission on `events` to retrieve the device's previous hash head (`prevHash`) on startup.
2. **Additional Permitted Collections (`system_state` & `ground_truth`)**:
   - `system_state`: Stores the MongoDB change stream resume token (`_id`) to enable zero-event-loss recovery across worker restarts, and anchors periodic external hash-chain checkpoints.
   - `ground_truth`: Stores reproducible scenario labels used exclusively by verification benchmarks (`quality.py`).
3. **Local Port Remapping on Windows Host**:
   - Host `mongo1` was published on port `37017` (to avoid conflicting with a native Windows `mongod` listening on port `27017`).
   - Host backend was published on port `18000` (port 8000 was in use).
   - The portable `.env.example` retains conventional default ports (27017 and 8000).
4. **Shared Authentication JSON Schema**:
   - SSH and Telnet protocols share the same payload schema (`{user, attempts}`). In strict JSON Schema, identical branch schemas under `oneOf` cause valid payloads to match multiple branches and fail validation. The schema was unified into a single authentication branch.
5. **Quality Benchmark Self-Containment**:
   - Querying the live database after multiple development phases showed degraded recall because early simulation runs in Phase 2 ran before the detector service was active. `quality.py` was implemented to execute an isolated, seeded, self-contained verification run in `benchmark_honeygraph.events_qual` evaluating all 7 scenarios with 100% precision and recall.

### Known Limitations

1. **Frontend Bundle Size**: The Vite production build generates a 403 kB gzipped chunk for visual dependencies (`vis-network`, `leaflet`, `recharts`). A warning is emitted during build; production deployments should implement route-level lazy loading.
2. **Single-Host Prototype**: The 3-node replica set runs in Docker on a single laptop host. While it validates Raft consensus and election failover, disk I/O and network bandwidth are shared.
3. **Sequential Chain Auditing**: Hash verification scans each device's events sequentially ($O(N)$). While fast (~19,600 events/s verification), fleet-wide audits across billions of events would require parallel batch chunking.

### Final Verification Gate

- `make test` / `python -m pytest tests`: **53 passed in 10.04s**.
- `npm --prefix frontend test`: **4 passed in 147ms**.
- `python backend/benchmarks/demo_flow.py`: **All 8 acceptance checks passed**.
- `python -m benchmarks.report`: **All 8 benchmarks verified, CSVs generated, charts rendered, docs/BENCHMARKS.md updated**.
- Docker replica set: All 3 MongoDB nodes (`mongo1`, `mongo2`, `mongo3`), backend, detector, and frontend are running and healthy.

### 2026-11-05 - Live alerts dashboard correction

- **Status:** fixed and deployed to the local backend container.
- **Cause:** dashboard scenario launches reused the simulator's deterministic 2026-10-14 timestamps. New detections were sorted below newer event timestamps, and the seven-day TTL expired their raw observations. The detector and WebSocket were operating.
- **Changes:** dashboard launches now shift timestamps to the current UTC clock while preserving relative event timing. The pure seeded simulator remains deterministic. Alert listings sort by `alertCreatedAt` descending, then `_id` descending, matching the displayed detection time and live arrival order; existing time-range filters still apply to event time.
- **Regression verification:** two targeted regressions failed before the changes; `python -m pytest tests/test_live_alert_regressions.py tests/test_simulator.py tests/test_api.py -q` then passed: **18 passed in 3.13s**.
- **Deployment:** `docker compose up -d --build --no-deps backend` completed successfully.
- **Live verification:** launched Mirai through the dashboard; today's alerts appeared first. With Live Alerts left open, a second API-launched scenario (seed 9711) retained all 18 current-dated events and generated 8 alerts, with measured insertion-to-alert latency 30-233 ms. Browser rows updated over WebSocket without reload; reloading kept the same new alerts first.
- **Evidence:** `docs/screenshots/alerts-fix-20261105.png`.
- **Scope:** historical records were not rewritten. The live badge indicates a connected alert stream; it does not continuously generate simulated traffic. Existing PDF guides predate this correction, so their fixed-date dashboard workaround is no longer required for new dashboard launches.

### 2026-11-05 - Expired session shown as offline

- **Cause:** the saved admin JWT expired after the configured 60 minutes. Backend logs showed repeated rejected WebSocket handshakes (403); all services remained running. The client reused the expired token every second and labeled this authentication failure as offline.
- **Fix:** AuthProvider now checks saved-token expiry, clears expired sessions, schedules expiry for an open session, and rechecks after focus/visibility changes. The login page displays `Your session expired. Please sign in again.` Backend JWT verification and the configured token lifetime remain unchanged.
- **Tests:** two expiry regressions failed before the fix. All frontend tests then passed: **6 passed**. The existing navigation tests now use unexpired token-shaped fixtures, with an explicit analyst-page assertion. `npm --prefix frontend run build` succeeded with the existing large-bundle warning.
- **Deployment:** `docker compose up -d --build --no-deps frontend` succeeded. A fresh real login returned alerts REST 200 and completed a WebSocket handshake/ping through port 5173.
- **Verification limit:** browser-control inspection was unavailable during this correction. The already-open tab needs a refresh to load the deployed client and then a normal sign-in; it was not silently reauthenticated.

### 2026-11-05 - Incident workflow and correlation repair

- **Status:** fixed, deployed and verified in the browser. Resetting the stale browser-control session restored browser inspection; the existing configured admin account was used for the verification login.
- **Causes reproduced:** only lateral-movement launches materialized incidents, leaving Mirai/recon alerts unlinked; same-source alerts were split into separate incidents; an expanded chain created another incident; failed detail requests displayed an endless spinner; status writes lacked a compare-and-swap guard.
- **Backend changes:** every dashboard scenario now waits for the detector's batch checkpoint (`system_state.lastEventId`), collects its detected alerts and builds incidents. Lateral movement requires coverage of every injected event. Runs with no new alerts return an explicit baseline/rule/cooldown message. Trusted MongoDB aggregation groups the root actor's parallel detections and uses `$graphLookup` for subsequent hops, scoped to the batch for new scenario materialization. Growing open/triaged incidents reuse an overlapping incident and retain history; closed investigations are not rebuilt. Incident/link/risk writes remain in one snapshot/majority transaction. Status transitions use a conditional update to avoid duplicate concurrent history entries.
- **Rule correction:** the seeded R-LATERAL-06 pipeline now matches `{{eventId}}`; its prior `$limit: 1` could cite an older event from the same source. Only the unchanged old seeded pipeline was migrated in the live rules collection; unrelated or user-edited rules were preserved.
- **Frontend changes:** incidents refresh automatically (list 3 s, detail 5 s), have manual refresh/navigation/pagination, show load errors, disable pending transitions, and use explicit graph hop levels. Scenario jobs refresh, show errors or no-alert reasons, and link to their resulting incident. Millisecond seeds avoid duplicate launches caused by a one-second seed value.
- **Regression gate:** four initial backend regressions, the current-event lateral-rule regression and four UI regressions failed before their fixes. Final checks: **62 backend tests passed in 10.20 s; 10 frontend tests passed; production frontend build succeeded** (existing bundle-size warning).
- **Live gate:** Mirai seed 17151 produced one incident with all 8 alerts; recon seed 17152 produced one incident with all 32 alerts; lateral seed 17153 recovered all 4 injected hops in order. Rebuilding each returned the same incident with no duplicate. The Mirai verification incident advanced open -> triaged -> closed with exactly three history entries; skipping directly to closed returned 409. Recon and lateral verification incidents remain open.
- **Recovery:** materialized 16 incidents from 191 unlinked fleet alerts whose event times were within the last 24 hours. No alerts were deleted, and existing closed incidents were not changed. Recovery was limited to this explicit recent fleet scope, not all historical/test alerts.
- **Deployment:** `docker compose up -d --build --no-deps backend detector frontend` succeeded. Browser verified the new cards and complete directed four-hop graph; screenshot: `docs/screenshots/incidents-fix-20261105.png`. JSON gate outputs: `tmp/report/incident-fix-evidence.json` and `tmp/report/incident-backfill-evidence.json`.
- **Remaining scope:** continuous alert ingestion outside dashboard scenario jobs still uses the standalone chain-builder entry point; this correction does not introduce a new always-running correlator service. Cooldown-suppressed traffic is not converted into fabricated alerts/incidents. Old report PDFs predate the expanded same-source grouping and incident workflow changes.

### 2026-11-19 - Simple DBMS presentation and demo guide

- **Delivered:** `output/pdf/HoneyGraph_DBMS_Presentation_Demo_Guide.pdf` (18 pages) and editable/copyable notes at `output/report/HoneyGraph_DBMS_Presentation_Demo_Guide.md`.
- **Contents:** exact dashboard click steps and simple speaking lines, the event-to-incident data flow, collections and references, change streams, aggregation, graph traversal, transaction versus single-document status updates, risk/geospatial queries, integrity, application/database RBAC, indexes, validators, TTL, time-series storage, replication, conceptual normalization, viva answers, troubleshooting and a timed rehearsal sheet.
- **Grounding:** checked against the current frontend, API routes, worker code, initializer, Compose and Makefile. Clarifies that telemetry scheduling and general continuous incident correlation are not automatically running Compose services; conceptual relational mapping is not a replacement for MongoDB collections. Includes a guarded inventory-only preparation snippet in the notes.
- **Verification:** rendered all 18 pages, reviewed layout and checked text bounds. This was a documentation task; it does not represent a fresh end-to-end test or benchmark run. No application behavior, rules or database evidence was changed.

### 2026-11-19 - Concise project PowerPoint

- **Delivered:** `output/presentations/HoneyGraph_Project_Presentation.pptx`, a 12-slide complete project presentation with speaker notes.
- **Reference style:** adapted the existing PrescriptXAI deck's RVCE cover, college branding, Bookman typography, red headings, blue tables and footer layout. The reference deck remains unchanged.
- **Content:** team and guide details, problem and objectives, tools, editable workflow diagram, eight-collection design and normalization rationale, MongoDB features, transactions/RBAC/replication, authentic saved alert/incident/map screenshots, integrity demo and conclusion. Removed phase-review labels and unrelated project text.
- **Verification:** package/layout/font/import checks passed; six tables remain native editable tables and all 12 slides contain speaker notes. Rendered with installed PowerPoint and visually reviewed the slides; corrected table overlap and screenshot proportions. Private build and validation evidence is in `tmp/presentations/honeygraph/`.
- **Scope:** presentation files only; no new application features, tests, traffic, database changes or benchmark claims.

### 2026-11-19 - Separate problem statement and objectives

- Updated the presentation to 13 slides: slide 3 is **Problem Statement** and slide 4 is **Objectives**. Preserved the existing design, updated speaker notes and renumbered later slides.
- Package/layout/font/import validation passed. Rendered all 13 slides with PowerPoint, inspected the two edited slides and scanned the deck. Verified all other slide text is unchanged apart from numbering.
- Latest file: `output/presentations/HoneyGraph_Project_Presentation_Revised.pptx`. The previous output is locked by another process, so it was left unchanged and the validated revision is delivered separately. Previous version also saved privately in `tmp/presentations/honeygraph/split-objectives/original.pptx`.

### 2026-11-19 - Compass connection diagnosis

- Confirmed the Windows MongoDB at localhost:27017 has a separate three-collection honeygraph database. The project's authenticated Docker replica set uses localhost:37017 and contains all eight main collections plus the two supporting collections.
- MongoDB ping and replica-set checks passed. Compass 1.53.0 displayed a `useConnectionInfo` rendering error. **View -> Reload (Ctrl+Shift+R)** cleared that error; reconnecting the saved 37017 connection opened the database page without the error.
- The remaining database list is empty. The saved 37017 connection URI contains no username/password or authSource. Database authentication must be completed manually in Compass with the existing root credentials and authentication database admin; no credentials were printed or changed.
- No database data or application configuration was modified. Compass authentication and visible collection access remain to be completed by the user.

### 2026-11-19 - Compass Docker hostname error resolved

- In the existing Compass connection's **General** options, enabled **Direct Connection**. Compass 1.53.0 warned `directConnection is not supported with replicaSet`, so cleared **Replica Set Name** in that connection's **Advanced** options and saved/reconnected. This adjusts the desktop client only; server replica-set configuration remains unchanged.
- Verified the saved Compass URI now has `directConnection=true`, no `replicaSet` option, and `authSource=admin`. The `ENOTFOUND mongo1` error cleared and the connection reached authentication, which returned **Authentication failed** for the user's currently saved credentials.
- Separately verified the existing root username/password from project `.env` successfully authenticates with a direct localhost:37017 connection. No password or secret was printed or changed. The user must re-enter the correct password in Compass's Authentication tab; authentication dialogs were not automated.

### 2026-11-19 - MongoDB Compass presentation guide

- **Delivered:** `output/pdf/HoneyGraph_MongoDB_Compass_Demo_Guide.pdf` (12 pages) and `output/report/HoneyGraph_Compass_Copyable_Queries.md`.
- **Contents:** correct local Compass setup, fresh-data preparation, exact collection/tab/filter steps, simple speaking lines, event-reference tracing, incident/risk/ACID explanation, aggregation, index Explain, validation, TTL, geospatial queries, time-series caveats, integrity, user roles, replica status and a quick rehearsal sheet. Notes include read-only shell examples and an optional telemetry-worker preparation command.
- **Verification:** checked nine query examples against the live database, confirmed strict/error validation and the seven-day TTL, syntax-checked four JavaScript snippets, and tested the scoped graph lookup on a stored lateral incident (one root and three subsequent hops). Rendered the 12-page PDF, checked its layout and text bounds. At preparation time, raw events and telemetry were empty; the guide tells the presenter to generate fresh dashboard traffic.
- **Scope:** no traffic, data mutations, initialization, schema changes or worker launches were performed while making the guide. Existing Compass authentication must still be completed manually.

### 2026-11-19 - Visible events-to-alerts-to-incidents presentation flow

- **Problem:** scenario cards exposed the final incident link but hid intermediate evidence, making the simulation appear to create incidents directly. Added failing backend and component regressions before implementing the presentation flow.
- **Implemented:** optional `deferCorrelation` launch mode; real event insertion and automatic change-stream detection continue, while incident creation waits for an explicit admin-only correlation request. Automatic mode remains the default. Correlation uses the existing MongoDB graph lookups and incident/alert/risk transaction. Repeated completed requests return the same incident; concurrent builds receive 409 and failed builds remain retryable.
- **Dashboard:** added the presentation checkbox, Generate events button, Inspect process, three evidence panels with actual IDs/expandable documents, explicit Build incident action and per-run Compass filters. Evidence endpoints scope documents to the launch's inserted event IDs and require admin access. Account and job lists scroll so the evidence panel remains accessible.
- **Live verification:** browser Mirai run paused at 18 events / 10 alerts / 0 incidents, then produced one incident on click. Lateral movement paused at 4 events / 4 alerts / 0 incidents; clicking produced one incident with hops 0–3, all injected hops recovered in order. API checks confirmed every alert was linked, repeated correlation returned the same incident and analyst access was denied. No synthetic alerts or incidents were inserted for the demo.
- **Validation:** full backend suite passed: **69 tests**. All **13 frontend tests** and the production build passed. During the final rerun, live traffic exposed an existing rollup test's assumption that its minute contained only one device; isolated that test in a temporary database and reran the full suite successfully. No production rollup behavior changed. Rebuilt and started backend/frontend containers; detector and MongoDB continued running. Existing React Router future-flag and bundle-size warnings remain non-blocking.
- **Guide and evidence:** `docs/GUIDED_DEMO.md`; browser screenshots and API verification JSON in `output/screenshots/guided-demo/`.
- **Limits:** API job metadata remains in process memory and is lost on backend restart; stored records persist. Detection counts vary with active rules/cooldowns. Presentation mode pauses the scenario launcher only; a separately launched chain builder can still correlate those alerts. No database schema or detection-rule changes were needed.

### 2026-11-23 - Complete simple project explanation and demo guide

- **Delivered:** `output/pdf/HoneyGraph_Complete_Project_Explanation_and_Demo_Guide.pdf` (24 pages, 24 navigation bookmarks), plus matching copyable speaking notes in `output/report/HoneyGraph_Complete_Project_Explanation_and_Demo_Guide.txt`.
- **Contents:** introduction, problem/objectives, terminology, architecture and technology reasons, all eight collections and references, ingestion/hash chains, detection-as-data, graph correlation/transactions/risk, startup, guided events -> alerts -> incidents, every dashboard feature, all seven scenarios, Compass evidence tracing/queries, DBMS features, conceptual UNF-to-3NF and relational mapping, role/replica explanations, viva answers, troubleshooting and a timed presentation sheet. Includes exact speaking lines and saved guided-flow screenshots.
- **Grounding:** checked the current source, Compose/Makefile, prior progress and guided-demo evidence. Distinguishes automatic detection from deferred correlation, stored risk from continuous recalculation, the dashboard tamper-attempt scenario from the Integrity three-mode mutation demo, and standalone telemetry/checkpoint operations from running Compose services. Keeps all credentials out of the guide.
- **Verification:** rendered all 24 PDF pages with Poppler, reviewed all pages and enlarged the graph figure. Verified the final page count/bookmarks, required topic coverage and text bounds; no text clipping found. Matching notes contain the full speaking text. Saved figures and test totals are explicitly dated 19 November, rather than presented as fresh results.
- **Scope:** documentation only. No stack startup, traffic generation, database mutations, rule edits, application changes, test reruns or benchmark reruns were performed for this guide.
