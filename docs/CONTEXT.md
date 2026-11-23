You are a senior backend/database engineer building HoneyGraph, a MongoDB-native threat-intelligence and attack-chain reconstruction engine for IoT networks (DBMS course project, RVCE CSE). Everything runs in software on simulated traffic. No real devices, no real exploit code. It is a defensive-security demo.

FIRST ACTION: save this entire message verbatim to docs/CONTEXT.md in the workspace, create docs/PROGRESS.md, then create an Implementation Plan artifact and a Task List artifact for the 12 phases (0-11) below. Do not start coding until both exist. I will send each phase as a separate prompt.

TECH STACK (fixed)
- MongoDB 7.0+ as a 3-node replica set in Docker Compose, keyFile auth enabled so RBAC is real
- Python 3.10+, PyMongo, FastAPI, Uvicorn, python-dotenv, pydantic, PyJWT, passlib[bcrypt], pytest, httpx
- React 18 + Vite + Tailwind CSS, vis-network, Recharts, Leaflet/react-leaflet
- Docker Compose for everything; Makefile with up, down, seed, simulate, test, bench, demo

REPO LAYOUT
honeygraph/
  docker-compose.yml, Makefile, .env.example, README.md
  docs/ (CONTEXT.md, PROGRESS.md, ARCHITECTURE.md, REPLICATION_SHARDING.md, BENCHMARKS.md)
  mongo/ (keyfile script, rs-init.sh, init_db.py, seed_rules.py)
  backend/app/ (main.py, config.py, db.py, auth.py, schemas.py, hashchain.py, rule_validator.py, ws.py, routers/)
  backend/workers/ (detector.py, chain_builder.py, risk_scorer.py, telemetry_rollup.py, integrity_checker.py)
  backend/simulator/ (devices.py, normal_traffic.py, scenarios/, ground_truth.py, cowrie_import.py, run.py)
  backend/benchmarks/, backend/tests/, backend/requirements.txt
  frontend/ (Vite + React + Tailwind)

NON-NEGOTIABLE DESIGN RULES
1. Detection triggering, correlation, retention and risk scoring use MongoDB features (change streams, aggregation, $graphLookup, TTL), not Python reimplementations.
2. Detection rules are documents in the rules collection, stored as aggregation pipelines, editable at runtime. Only an allow-list of read-only stages is executable; $out, $merge, $function, $where, $accumulator and cross-collection $lookup are rejected.
3. events is a REGULAR collection (change streams watch it). device_telemetry is a TIME-SERIES collection used only for per-minute rollups, written outside transactions. Reason: time-series collections do not support change streams or transactions.
4. Creating an incident, linking its alerts and updating risk_scores happen in ONE multi-document transaction.
5. SHA-256 hash chain is PER DEVICE: hash = SHA256(prevHash || canonical(event fields)). No global ordering point.
6. Eight collections: devices, events, device_telemetry, rules, alerts, incidents, risk_scores, users. Allowed extras: system_state (resume token, checkpoints) and ground_truth (benchmark labels only).
7. No secrets in the repo; use .env and generated keyfile.

WORKING RULES
- Work phase by phase. Each phase ends with a verification gate: run the commands, show output, fix failures before finishing.
- Update docs/PROGRESS.md after every phase (status, decisions, deviations, known issues).
- Small typed commented modules; tests for every phase.
- Never rewrite completed phases unless a test fails.

Reply only with: confirmation that docs/CONTEXT.md and docs/PROGRESS.md exist, and the two artifacts. Then wait for Phase 0.
