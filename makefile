# ==== Простая Makefile для Alembic и Docker ==================================

DC ?= docker compose
SERVICE ?= app # Имя сервиса приложения в docker-compose.yml
DB_SERVICE ?= db
ALEMBIC ?= alembic
ENV_FILE ?= .env
include $(ENV_FILE)
MSG ?= auto
V ?=

DC_EXEC_APP = $(DC) exec -T $(SERVICE)
DC_EXEC_DB  = $(DC) exec -T $(DB_SERVICE)

.PHONY: help compose-up compose-down compose-down-v compose-restart compose-logs bash rev rev-up rev-down up-to down-to db-reset hard-reset pre-commit pytest ci-checks

help:
	@echo "Commands:"
	@echo "  compose-up          — build and start containers"
	@echo "  compose-down        — stop containers"
	@echo "  compose-down-v      — stop containers + remove volumes"
	@echo "  compose-restart     — restart containers"
	@echo "  compose-logs        — show logs"
	@echo "  bash                — shell in app container"
	@echo "  rev MSG=msg         — create alembic revision"
	@echo "  rev-up              — upgrade DB to head"
	@echo "  rev-down            — downgrade DB one step"
	@echo "  up-to V=rev         — upgrade to revision"
	@echo "  down-to V=rev       — downgrade to revision"
	@echo "  db-reset            — drop & create DB"
	@echo "  hard-reset          — drop & create DB + migrate"
	@echo "  pre-commit          — run all pre-commit hooks on all files"
	@echo "  pytest              — run tests in bot/tests"
	@echo "  ci-checks           — run CI checks in with pre-commit bot/tests  "

# Docker
compose-up:
	$(DC) up -d --build

compose-down:
	$(DC) down

compose-down-v:
	$(DC) down -v

compose-restart:
	$(DC) restart

compose-logs:
	$(DC) logs -f --tail=20

bash:
	$(DC_EXEC_APP) bash || $(DC_EXEC_APP) sh

# Alembic
rev:
	@if [ -z "$(MSG)" ]; then echo "MSG required"; exit 1; fi
	$(ALEMBIC) revision -m "$(MSG)" --autogenerate

rev-up:
	$(ALEMBIC) upgrade head

rev-down:
	$(ALEMBIC) downgrade -1

up-to:
	@if [ -z "$(V)" ]; then echo "V required"; exit 1; fi
	$(ALEMBIC) upgrade $(V)

down-to:
	@if [ -z "$(V)" ]; then echo "V required"; exit 1; fi
	$(ALEMBIC) downgrade $(V)

# Database reset
db-reset:
	$(DC_EXEC_DB) psql -U $(DB_USER) -d postgres -c "DROP DATABASE IF EXISTS \"$(DB_DATABASE)\";"
	$(DC_EXEC_DB) psql -U $(DB_USER) -d postgres -c "CREATE DATABASE \"$(DB_DATABASE)\" WITH OWNER \"$(DB_USER)\";"

hard-reset: db-reset rev-up
	@echo "DB reset and migrations applied"

# Pre-commit
pre-commit:
	@echo "Running pre-commit hooks on all files..."
	pre-commit run --all-files


pytest:
	@echo "Running tests on all files in test directory..."
	pytest -vs bot/tests
ci-checks: pre-commit
	@echo "Running CI checks..."
	poetry run black --check .
	poetry run isort --check-only --profile black .
	poetry run ruff check .
	poetry run ruff format --check .
	poetry run mypy .
	@echo "All CI checks passed! ✅"
