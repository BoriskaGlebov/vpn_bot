# ==== Makefile для Docker Compose + Alembic + Tests + CI ======================

# -------------------- Основные переменные --------------------
DC ?= docker compose
STAGE ?= develop
SERVICE ?= vpn_bot
DB_SERVICE ?= postgres
ALEMBIC ?= alembic
MSG ?=
PYTHON ?= poetry run python

# Compose файлы
COMPOSE_COMMON = -f docker-compose.common.yml
COMPOSE_DEV    = $(COMPOSE_COMMON) -f docker-compose.develop.yml
COMPOSE_PROD   = $(COMPOSE_COMMON) -f docker-compose.prod.yml
COMPOSE_LOCAL  = $(COMPOSE_COMMON) -f docker-compose.local.yml


ifeq ($(STAGE),prod)
  COMPOSE_FILES = $(COMPOSE_PROD)
  ENV_FILE = .env
else ifeq ($(STAGE),local)
  COMPOSE_FILES = $(COMPOSE_LOCAL)
  ENV_FILE = .env.local
else
  COMPOSE_FILES = $(COMPOSE_DEV)
  ENV_FILE = .env.local
endif


# ===================== Основные команды =====================

.PHONY: help compose-up compose-down rev rev-up rev-down \
        infra-up infra-down pre-commit ci-checks \
        init-db init-redis run-bot full-up

help:
	@echo ""
	@echo "🧭 Доступные команды Makefile:"
	@echo "────────────────────────────────────────────"
	@echo "  compose-up           — поднять контейнеры (основной compose)"
	@echo "  compose-down         — остановить контейнеры"
	@echo ""
	@echo "  run-bot              — запуск основного бота (bot/main.py)"
	@echo "  run-api              — запуск api сервиса (api/main.py)"
	@echo ""
	@echo "  rev MSG='msg'        — создать новую Alembic ревизию"
	@echo "  rev-up               — применить все миграции"
	@echo "  rev-down             — откатить последнюю миграцию"
	@echo ""
	@echo "  pre-commit           — запустить pre-commit проверки"
	@echo "  ci-checks            — полный набор проверок (black, isort, ruff, mypy)"
	@echo "  pytests              — запустить тесты (с поддержкой -m)"
	@echo ""
	@echo "────────────────────────────────────────────"
	@echo "  Stage: $(STAGE)"
	@echo "  Env file: $(ENV_FILE)"
	@echo "  Compose files: $(COMPOSE_FILES)"
	@echo ""


# ===================== Docker Compose =====================

compose-up:
	@echo "🚀 Поднимаем контейнеры..."
	$(DC) $(COMPOSE_FILES) --env-file $(ENV_FILE) up -d --build

compose-down:
	@echo "🛑 Останавливаем контейнеры..."
	$(DC) $(COMPOSE_FILES) --env-file $(ENV_FILE) down


# ===================== Alembic =====================

rev:
	@if [ -z "$(MSG)" ]; then echo "❌ Укажи сообщение: make rev MSG='init db'"; exit 1; fi
	$(ALEMBIC) revision -m "$(MSG)" --autogenerate

rev-up:
	@echo "📈 Применяем миграции..."
	$(ALEMBIC) upgrade head

rev-down:
	@echo "📉 Откатываем последнюю миграцию..."
	$(ALEMBIC) downgrade -1


# ===================== Tests & Code Quality =====================

pre-commit:
	@echo "🔧 Запускаем pre-commit hooks..."
	pre-commit run --all-files

ci-checks: pre-commit
	@echo "🧪 Проверки кода (CI/CD)..."
	poetry run black --check .
	poetry run isort --check-only --profile black .
	poetry run ruff check .
	poetry run ruff format --check .
	poetry run mypy .
	make pytests
	@echo "✅ Все проверки пройдены!"



# ===================== Инициализация и запуск =====================
run-bot: rev-up
	@echo "🤖 Запускаем бота..."
	$(PYTHON) -m bot.main
run-api: rev-up
	@echo "🤖 Запускаем API сервис..."
	$(PYTHON) -m api.main

pytests:
	@echo "🧪 Запускаем тесты..."
	pytest -vs $(if $(m),-m $(m),) bot/tests
	pytest -vs $(if $(m),-m $(m),) api/tests
