# HoneyGraph Implementation Plan

Source of requirements: [CONTEXT.md](CONTEXT.md).

## Phase sequence

The initial request does not specify phase contents. Populate each phase from its separate user prompt before implementation; do not infer or reorder scopes.

| Phase | Scope | Verification gate |
| --- | --- | --- |
| 0 | Three-node authenticated MongoDB replica set, initialization job, generated keyfile, environment contract, service placeholders, and operational Make targets | `docker compose up -d`; prove 1 PRIMARY + 2 SECONDARY and reject unauthenticated access |
| 1 | Idempotent database bootstrap: ten permitted collections, strict validators, indexes and TTL, telemetry time-series options, least-privilege RBAC users | Run bootstrap twice and `pytest backend/tests/test_schema.py`; prove valid/invalid schemas and positive/negative role permissions |
| 2 | Deterministic 500-device simulator, normal traffic, seven labeled abstract scenarios, pluggable API/direct sinks, optional Cowrie mapping, and scoped tamper demonstration | Pytest determinism/schema/labels; run 30 logical seconds and report protocol/scenario counts |
| 3 | FastAPI batch ingestion, deterministic canonical hashing, concurrency-safe per-device chains, transactional failure rollback, insertion timing, simulator HTTP sink, and chain verifier | API/chain/failure tests; ingest and verify 100,000 events; report throughput |
| 4 | Change-stream detection-as-data worker, live validated rule cache, resume tokens, cooldown dedupe, majority alerts, and ten seeded rules | Run scenarios 1–3, restart/resume proof, live edit proof, forbidden-stage tests, and p50/p95 latency report |
| 5 | Bidirectional `$graphLookup` attack-chain reconstruction, transactional incidents/alert links/risk, exponential MongoDB risk aggregation, and idempotent minute telemetry rollups | Prove ordered lateral chain, rebuild idempotency, transaction rollback, score decay, rollup idempotency, and full regression suite |
| 6 | Per-device hash-chain integrity checking, exact tamper classification, externally anchored truncation checkpoints, and scoped tamper demonstrations | Test clean/modified/deleted/reordered/truncated chains; verify 100,000+ clean events and report throughput |
| 7 | JWT/bcrypt authentication, analyst/admin REST RBAC, alert WebSocket change stream, typed OpenAPI routes, and administration of rules/users/scenarios/integrity | HTTPX/TestClient integration coverage for every router, 401/403 and validation gates, strict incident transitions, and sub-second WebSocket delivery |
| 8 | Responsive React 18 SOC dashboard with live alerts, attack-chain visualization, risk map/charts, integrity, rule administration, scenarios/users, role-aware navigation, and production Nginx container | Vite production build, component tests, live container/proxy check, and screenshots of every seeded page |
| 9 | Awaiting Phase 9 prompt | Define from prompt, run commands, show output, fix failures |
| 10 | Awaiting Phase 10 prompt | Define from prompt, run commands, show output, fix failures |
| 11 | Awaiting Phase 11 prompt | Define from prompt, run commands, show output, fix failures |

## Implementation constraints

- Use the fixed stack and repository layout in CONTEXT.md.
- Keep detection, correlation, retention, and scoring MongoDB-native.
- Store runtime-editable rules as aggregation pipelines; enforce the read-only allow-list and all stated exclusions.
- Keep events regular and telemetry time-series; rollups occur outside transactions.
- Atomically create incidents, link alerts, and update risk scores in one transaction.
- Maintain per-device SHA-256 hash chains with canonical event fields.
- Use only the eight required collections and the two permitted extras.
- Generate the keyfile and keep secrets outside versioned files.
- Implement small, typed, commented modules and tests for every phase.
- Preserve completed phases unless a failing test requires changes.

## Phase completion procedure

1. Record the supplied scope, deliverables, and verification commands in these artifacts.
2. Implement the current phase and its tests.
3. Run its verification gate, retain command output, and fix failures before finishing.
4. Update PROGRESS.md with status, decisions, deviations, known issues, and verification evidence.
5. Wait for the next phase prompt.
