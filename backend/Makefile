.DEFAULT_GOAL := help
RUN := uv run --frozen
DB_CONTAINER := ghostseats-db
LOCAL_TEST_DB := postgresql://postgres:ghostseats@localhost:5433/ghostseats_test

.PHONY: help sync dev test test-db lint fmt typecheck check db-up db-create db-down db-init seed seed-history policies fake-node qr vapid-keys load-check muse-check image deploy

help: ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-14s %s\n", $$1, $$2}'

sync: ## Install dependencies from uv.lock
	uv sync --frozen

dev: ## Run the API with reload (reads .env)
	$(RUN) uvicorn app.main:build --factory --reload --port 8000 --no-access-log

test: ## Unit, service and in-memory contract tests
	$(RUN) pytest

test-db: ## Everything, incl. Postgres tests. Uses ghostseats_test: tests TRUNCATE every table
	TEST_DATABASE_URL=$${TEST_DATABASE_URL:-$(LOCAL_TEST_DB)} $(RUN) pytest

lint: ## Ruff lint and format check
	$(RUN) ruff check .
	$(RUN) ruff format --check .

fmt: ## Apply ruff formatting and safe fixes
	$(RUN) ruff check --fix .
	$(RUN) ruff format .

typecheck: ## mypy --strict on app/
	$(RUN) mypy

check: lint typecheck test ## Lint, typecheck, test

db-up: ## Start a local Postgres + Timescale (Toolkit included) on :5433
	docker start $(DB_CONTAINER) 2>/dev/null || docker run -d --name $(DB_CONTAINER) -p 5433:5432 \
		-e POSTGRES_PASSWORD=ghostseats timescale/timescaledb-ha:pg16

db-create: ## Create the local ghostseats (dev) and ghostseats_test databases if missing
	@for db in ghostseats ghostseats_test; do \
		docker exec $(DB_CONTAINER) psql -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$$db'" | grep -q 1 \
		|| docker exec $(DB_CONTAINER) psql -U postgres -qc "CREATE DATABASE $$db"; \
	done; echo "databases ready: ghostseats, ghostseats_test"

db-down: ## Stop the local database
	docker stop $(DB_CONTAINER)

db-init: ## Apply schema.sql to DATABASE_URL
	$(RUN) python -m scripts.db apply sql/schema.sql

seed: ## Apply seed.sql to DATABASE_URL
	$(RUN) python -m scripts.db apply sql/seed.sql

policies: ## Compression, retention and the history aggregate (D31, D32)
	$(RUN) python -m scripts.db policies

seed-history: ## Write HISTORY_WINDOW_H of change-only readings for every seat
	$(RUN) python -m scripts.seed_history

fake-node: ## Interactive stand-in for the Pi bridge
	$(RUN) python -m scripts.fake_node

qr: ## Printable QR sheet for /seat/<id> (ORIGIN=https://…)
	$(RUN) python -m scripts.seat_qr --origin "$(ORIGIN)"

vapid-keys: ## Generate a VAPID key pair for .env
	$(RUN) python -m scripts.vapid_keys

load-check: ## 500 polling clients + 50 fake nodes against BASE_URL (creates load-test seats)
	$(RUN) python -m scripts.load_check --setup --base-url "$${BASE_URL:-http://localhost:8000}" $(ARGS)

seed-demo: ## One simulated host per catalog course, so every topic finds someone (D56)
	$(RUN) python -m scripts.seed_demo_hosts

cards: ## Generate the match card images with Muse Image into OUT (default out/cards) (D52)
	$(RUN) python -m scripts.card_images --out "$(or $(OUT),out/cards)"

muse-check: ## One live call per AI function with the MUSE_API_KEY in .env, with latency (D38)
	$(RUN) python -m scripts.muse_check

image: ## Build the deploy image locally (FRONTEND_DIR relative to the repo root, default frontend)
	cd .. && DOCKER_BUILDKIT=1 docker build -f backend/Dockerfile --build-arg FRONTEND_DIR=$${FRONTEND_DIR:-frontend} -t ghostseats-api:local .

deploy: ## Rolling deploy of REF (default origin/main) to HOSTS="root@ip1 root@ip2" (D36)
	./deploy/deploy.sh $(REF)
