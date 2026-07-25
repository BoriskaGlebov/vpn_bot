# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

VPN Boriska Bot — a Telegram bot + internal HTTP API for selling/managing VPN access
(Amnezia/WireGuard and XRay/3x-ui), subscriptions, referrals, and an MTProto proxy (telemt).
Comments, docstrings, and commit messages in this repo are written in Russian; match that
convention when editing existing files.

Three independently-runnable services live in one repo:
- `bot/` — FastAPI app wrapping an **aiogram 3** Telegram bot (webhook or polling). Entry point `bot/main.py`, served on port 8088 under root path `/bot`.
- `api/` — internal FastAPI app + **SQLAdmin** admin UI. This is the only service that talks to Postgres directly. Entry point `api/main.py`, served on port 8089 under root path `/api`.
- `ai_service/` — optional AI/LLM service (Yandex AI Studio + LangChain + pgvector), currently mostly disabled/WIP (see commented-out `ai` router wiring in `bot/main.py`).

`shared/` holds code used by more than one service: pydantic-settings config loaders (`shared/config/`), Redis/HTTPX client interfaces (`shared/interfaces/`), and enums.

## Commands

Dependency management is via Poetry (Python 3.12).

```bash
poetry install --with dev          # install app + dev tooling
poetry install --without dev       # production install
```

### Tests

```bash
pytest -q                          # run full suite (config in pytest.ini)
pytest bot/tests/unit/test_vpn_service.py            # single file
pytest bot/tests/unit/test_vpn_service.py::test_name # single test
pytest -m vpn                      # run tests under a marker (see markers in pytest.ini: admin, dao, dialogs, help, middleware, subscription, users, utils, vpn, bot, integration, referrals, news)
```

Tests live in `bot/tests/{unit,integration}/` and `api/tests/`. `pytest-asyncio` is in `auto` mode, so async test functions don't need `@pytest.mark.asyncio` for the loop to be picked up, but the existing tests do decorate them explicitly — follow that pattern for consistency. CI runs tests with `ENV_FILE=.env.test` and secrets injected as env vars (see `.github/workflows/ci.yml`); locally you'll need a comparable `.env`/`.env.local`.

### Lint / type-check / format

Mirrors CI (`.github/workflows/ci.yml`) and pre-commit (`.pre-commit-config.yaml`) exactly — run these before considering a change done:

```bash
poetry run black --check .
poetry run isort --check-only --profile black .
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy .
```

`ruff.toml` and `pyproject.toml`'s `[tool.mypy]` both exclude `*/migrations/*`, `bot/tests/`, `api/tests/`, and `bot/vpn/utils/` (mypy only) from checks — don't expect those directories to be clean under mypy.

### Database migrations

Despite the README saying `bot/migrations`, Alembic is actually configured (`alembic.ini`) with `script_location = api/migrations`, and migrations only exist under `api/`. Run from repo root:

```bash
alembic upgrade head
alembic revision --autogenerate -m "message"
```

### Running the services locally

```bash
python bot/main.py     # aiogram bot + FastAPI, http://localhost:8088/bot/docs
python api/main.py      # internal API + SQLAdmin, http://localhost:8089/api/docs
```

Or via Docker Compose (`docker-compose.{develop,local,prod,common}.yml`), e.g.:

```bash
docker compose -f docker-compose.develop.yml up -d --build
```

## Configuration

Settings are loaded via `pydantic-settings` (`shared/config/app_config.py`) from a layered
source: `app_config.toml` (base) + `app_config.{develop,local}.toml` (stage-specific override,
deep-merged) plus `.env` / `.env.dev` / `.env.local` (later files override earlier ones; stage
is chosen by the `STAGE` env var). Unknown `.env` keys are silently ignored. See `README.md` for
the full environment variable reference (proxy/XRay/DB/Redis/S3/AI groups) — it's kept current
and shouldn't be duplicated here.

## Architecture

### Layering (bot service)

Each bot feature module (`bot/users`, `bot/subscription`, `bot/vpn`, `bot/payment`,
`bot/referrals`, `bot/news`, `bot/scheduler`, `bot/admin`, ...) follows the same layers:

```
router.py   aiogram Router / handlers — user-facing Telegram interaction (often paired with
            aiogram-dialog windows under a dialogs/ or keyboards/ subfolder)
services.py business logic, orchestrates one or more adapters
adapter.py  wraps APIClient calls to the internal api/ service (HTTP, not direct DB access)
schemas.py  pydantic request/response models for the adapter <-> api boundary
```

The bot process never talks to Postgres directly — all persistence goes through HTTP calls
to the `api/` service via `bot/integrations/api_client.py` (`APIClient`). VPN/XRay panel calls
go through the same `APIClient` abstraction, just pointed at the panel host instead of the
internal API (see `ThreeXUIAdapter` in `bot/vpn/utils/x_ray_config.py`).

`bot/core/container.py` (`Container`) is the composition root: it constructs the shared
`RedisClient`/`APIClient`, then adapters, then services, then wires them into each `*Router`
inside the FastAPI `lifespan` in `bot/main.py`. When adding a new bot feature, add its
adapter/service to `Container.__init__` and instantiate/register its router in
`bot/main.py`'s `lifespan`, following the existing modules as a template.

### Layering (api service)

Each `api/<feature>` module follows a more traditional FastAPI-with-SQLAlchemy layering:

```
router.py    FastAPI routes, tagged per feature (see tags_metadata in api/main.py)
services.py  business logic
dao.py       SQLAlchemy data access (extends api/core/dao/base.py)
models.py    SQLAlchemy ORM models
schemas.py   pydantic I/O schemas
admin.py     SQLAdmin ModelView registered onto the `Admin` instance in api/main.py
dependencies.py  FastAPI dependency-injection helpers (DB session, current user, etc.)
```

Errors follow a two-tier scheme: `api/app_error/base_error.py` (`AppError`, generic domain
errors) and `api/app_error/api_error.py` (`APIError`, HTTP-facing errors), both wired to
handlers in `api/core/exceptions/handlers/` and registered on the FastAPI app in `api/main.py`.
The bot side mirrors this with its own `bot/app_error/` for translating API error responses
back into user-facing Telegram messages.

Middleware order matters and is applied in `api/main.py` in this sequence: `LogContextMiddleware`
→ `AuthMiddleware` → `RequestLoggingMiddleware` → `DBSessionMiddleware` → `ExceptionLoggingMiddleware`.
The bot side registers its middlewares (`ErrorHandlerMiddleware`, `UserActionLoggingMiddleware`,
`UserContextMiddleware`) inside the `lifespan` function in `bot/main.py`, not at app-creation time.

### Payments

`bot/payment/providers/` implements payment providers behind a `BasePaymentProvider` interface
(currently Platega, `platega.py`). `PaymentService`/`PaymentWebhookService` in
`bot/payment/services.py` handle transaction creation and the `/payment-webhook` endpoint in
`bot/main.py`; webhook events are parsed by the active provider then dispatched to
subscription/notification services.

### Scheduler

A daily job (`apscheduler`, cron trigger at 08:00) is registered in `bot/main.py`'s `lifespan`
via `bot/scheduler/utils/scheduler_cron.py`; it drives subscription expiry reminders through
`SchedulerBotService`. The `api/scheduler` module exposes API-side endpoints for the same domain.

### VPN backends

Two VPN backends are supported side by side: Amnezia/WireGuard (config generation and SSH-based
management in `bot/vpn/utils/amnezia_*.py`) and XRay/3x-ui (panel automation in
`bot/vpn/utils/x_ray_config.py`, `ThreeXUIAdapter` + `XRayRegistry`). `XRayRegistry` is built once
in `Container.__init__` from `settings_bot.vpn.nodes` (one `APIClient`+adapter per configured
node/panel).
