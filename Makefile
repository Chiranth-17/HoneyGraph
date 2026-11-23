COMPOSE := docker compose
PYTHON ?= python

ifeq ($(OS),Windows_NT)
KEYFILE_COMMAND := powershell -NoProfile -ExecutionPolicy Bypass -File mongo/generate-keyfile.ps1
else
KEYFILE_COMMAND := sh mongo/generate-keyfile.sh
endif

.PHONY: keyfile up down logs mongosh seed seed-rules simulate test demo bench

keyfile:
	$(KEYFILE_COMMAND)

up: keyfile
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

mongosh:
	$(COMPOSE) exec mongo1 sh -c 'mongosh --username "$$MONGO_INITDB_ROOT_USERNAME" --password "$$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin'

simulate:
	cd backend && $(PYTHON) -m simulator.run --devices 500 --rate 2000 --duration 60 --scenarios all --seed 42

seed-rules:
	$(PYTHON) mongo/seed_rules.py

seed:
	$(PYTHON) mongo/init_db.py
	$(PYTHON) mongo/seed_rules.py

test:
	cd backend && $(PYTHON) -m pytest tests

demo:
	$(PYTHON) backend/benchmarks/demo_flow.py

bench:
	cd backend && $(PYTHON) -m benchmarks.ingest && $(PYTHON) -m benchmarks.indexes && $(PYTHON) -m benchmarks.latency && $(PYTHON) -m benchmarks.quality && $(PYTHON) -m benchmarks.chains && $(PYTHON) -m benchmarks.integrity && $(PYTHON) -m benchmarks.storage && $(PYTHON) -m benchmarks.failover && $(PYTHON) -m benchmarks.report
