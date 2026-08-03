<p align="center">
  <h1 align="center">VPN Boriska Bot</h1>
  <p align="center">Telegram-бот + внутренний HTTP API для продажи и управления VPN-доступом (Amnezia/WireGuard и XRay/3x-ui), подписками, рефералами и MTProto-прокси.</p>
</p>

<p align="center">
  <img alt="CI" src="https://github.com/BoriskaGlebov/vpn_bot/actions/workflows/ci.yml/badge.svg">
  <img alt="Python" src="https://img.shields.io/badge/python-3.12-blue">
  <img alt="Code style" src="https://img.shields.io/badge/code%20style-black-000000">
  <img alt="Types" src="https://img.shields.io/badge/types-mypy-blue">
</p>

---

## Содержание

- [Обзор](#обзор)
- [Архитектура](#архитектура)
- [Технологии](#технологии)
- [Структура репозитория](#структура-репозитория)
- [Требования](#требования)
- [Быстрый старт](#быстрый-старт)
- [Конфигурация](#конфигурация)
  - [Переменные окружения (`.env`)](#переменные-окружения-env)
  - [Настройки приложения (`app_config*.toml`)](#настройки-приложения-app_configtoml)
- [Запуск](#запуск)
- [Миграции базы данных](#миграции-базы-данных)
- [Тесты и качество кода](#тесты-и-качество-кода)
- [Платежи](#платежи)
- [MTProto-прокси (telemt)](#mtproto-прокси-telemt)
- [Nginx](#nginx)
- [Эксплуатационные заметки](#эксплуатационные-заметки)
- [Лицензия](#лицензия)

---

## Обзор

Проект решает три связанные задачи одним репозиторием:

- **Продажа VPN-доступа** через Telegram — выдача конфигов Amnezia/WireGuard и XRay, лимиты на пользователя, несколько VPN-нод/локаций.
- **Подписки и монетизация** — тарифы (стандарт/премиум/founder), триал-период, оплата картой через платёжный шлюз (Platega) или вручную администратором, реферальная программа с бонусами.
- **MTProto-прокси** (telemt) как дополнительный продукт для тех же пользователей.

Технически это два независимо разворачиваемых FastAPI-приложения (bot-сервис и api-сервис) плюс общий код в `shared/`.

## Архитектура

| | `bot/` | `api/` |
|---|---|---|
| Что это | Telegram-бот на **aiogram 3**, обёрнутый в FastAPI (webhook/polling) | Внутренний HTTP API + админ-панель **SQLAdmin** |
| Кто вызывает | Telegram, платёжный шлюз (webhook) | Только `bot/` (по HTTP, с общим секретом) |
| БД | Не имеет прямого доступа к БД | Единственный сервис, работающий с PostgreSQL напрямую |
| Порт / root path | `8088` / `/bot` | `8089` / `/api` |
| Swagger | `http://localhost:8088/bot/docs` | `http://localhost:8089/api/docs` |
| Health-check | `GET /bot/health` | `GET /api/health` |
| Точка входа | `bot/main.py` | `api/main.py` |

Слои внутри каждого фичевого модуля выдержаны единообразно:

- **`bot/<feature>/`**: `router.py` (хендлеры aiogram) → `services.py` (бизнес-логика) → `adapter.py` (HTTP-вызовы к `api/` через `bot/integrations/api_client.py`) → `schemas.py`.
  Процесс `bot/` никогда не обращается к Postgres напрямую — только через `api/`.
- **`api/<feature>/`**: `router.py` (FastAPI-роуты) → `services.py` → `dao.py` (SQLAlchemy, наследует `api/core/dao/base.py`) → `models.py` (ORM) → `schemas.py` → `admin.py` (SQLAdmin-представление).

Composition root бота — `bot/core/container.py` (`Container`): здесь собираются общий `RedisClient`/`APIClient`, адаптеры и сервисы, которые затем передаются роутерам в `lifespan` (`bot/main.py`).

`shared/` — код, используемый обоими сервисами: загрузка конфигурации (`shared/config/`), интерфейсы Redis/HTTPX-клиентов (`shared/interfaces/`), общие enum'ы.

`ai_service/` и `bot/ai/` — заготовки под AI/LLM-функциональность (Yandex AI Studio + LangChain + pgvector), на данный момент в основном отключены/не завершены и не участвуют в рабочем флоу.

## Технологии

- **Python 3.12**, [Poetry](https://python-poetry.org/) — управление зависимостями
- **aiogram 3** — Telegram-бот
- **FastAPI** + **Uvicorn** — оба HTTP-сервиса
- **SQLAlchemy 2 (async)** + **Alembic** — доступ к БД и миграции
- **PostgreSQL** — основная БД
- **Redis** — кэш, блокировки, хранение временных сообщений/состояний
- **SQLAdmin** — админ-панель поверх `api/`
- **APScheduler** — плановая проверка подписок (истечение, удаление конфигов)
- **httpx** — HTTP-клиент для вызовов `bot/` → `api/` и к внешним панелям (3x-ui, платёжный шлюз)
- **loguru** — логирование
- **pytest / pytest-asyncio / pytest-cov** — тесты и покрытие
- **black, isort, ruff, mypy, pydocstyle, pre-commit** — статический анализ и стиль кода
- **Docker / Docker Compose** — развёртывание

## Структура репозитория

```
vpn_bot/
├── bot/                  # Telegram-бот + FastAPI (webhook/polling)
│   ├── payment/          # Провайдеры оплаты (Platega), вебхук платежей
│   ├── subscription/     # Подписки, тарифы
│   ├── vpn/               # Amnezia/WireGuard + XRay/3x-ui интеграции
│   ├── referrals/         # Реферальная программа
│   ├── scheduler/         # Ежедневная проверка подписок (cron)
│   ├── admin/, users/, news/, help/, ...
│   ├── core/               # Container (DI), конфигурация, фильтры
│   ├── integrations/       # APIClient — HTTP-клиент к api/
│   └── tests/{unit,integration}/
├── api/                   # Внутренний API + SQLAdmin
│   ├── payment/, subscription/, vpn/, referrals/, users/, scheduler/, admin/, news/
│   ├── core/               # BaseDAO, конфигурация, middleware, exception handlers
│   ├── migrations/         # Alembic (несмотря на alembic.ini рядом с корнем — ревизии лежат здесь)
│   └── tests/unit/
├── shared/                 # Общий код bot/ и api/
│   ├── config/              # Загрузка настроек (toml + .env)
│   ├── interfaces/          # Абстракции Redis/HTTPX-клиентов
│   └── enums/
├── ai_service/, bot/ai/     # AI/LLM-заготовки (WIP, в основном отключены)
├── telemt-config/           # Конфигурация MTProto-прокси (telemt)
├── app_config.toml,
│   app_config.develop.toml,
│   app_config.local.toml    # Несекретные настройки приложения (см. "Конфигурация")
├── .env.example              # Шаблон секретов (обратите внимание — с пробелом в конце имени файла)
├── docker-compose.*.yml      # common / develop / local / prod
├── nginx.conf, nginx_test.conf
├── makefile                  # Частые команды (см. ниже)
└── pyproject.toml, ruff.toml, pytest.ini, alembic.ini
```

## Требования

- Python 3.12
- Poetry
- PostgreSQL 14+
- Redis 6+
- (опционально) S3-совместимое хранилище — для медиа справки (например, Yandex Object Storage)
- Docker + Docker Compose — для развёртывания через контейнеры

> В `docker-compose.*.yml` этого репозитория **нет** сервисов Postgres/Redis — они подключаются как внешние (либо локально установлены, либо подняты отдельным compose-стеком в тех же Docker-сетях `infrastructure_net`/`shared_net`).

## Быстрый старт

```bash
git clone git@github.com:BoriskaGlebov/vpn_bot.git
cd vpn_bot

# Зависимости
poetry install --with dev        # с dev-инструментами (тесты, линтеры)
# poetry install --without dev   # только рантайм, для прод-образа

# Секреты — скопировать шаблон (обратите внимание на пробел в оригинальном имени)
cp ".env.example " .env
# Заполнить BOT_TOKEN, DB_PASSWORD, REDIS_PASSWORD, INTERNAL_API_SECRET и т.д. — см. ниже

# Несекретные настройки — свериться с app_config.toml / app_config.develop.toml
# (хосты VPN-нод, тарифы, лимиты и пр.) и поправить под своё окружение

# Миграции
alembic upgrade head    # или: make rev-up

# Запуск обоих сервисов (в двух терминалах)
python bot/main.py      # http://localhost:8088/bot/docs
python api/main.py      # http://localhost:8089/api/docs
```

Либо через Docker Compose — см. [«Запуск»](#запуск).

## Конфигурация

Настройки собираются `pydantic-settings` из **двух источников**, и это важно не путать:

1. **`.env` / `.env.dev` / `.env.local`** — только секреты и то, что меняется от инстанса к инстансу (токены, пароли, ключи API). Более специфичный файл переопределяет более общий. Актуальный список — в `.env.example ` (да, с пробелом в конце имени файла).
2. **`app_config.toml` (база) + `app_config.develop.toml` / `app_config.local.toml`** (stage-специфичный, глубоко мёрджится поверх базы) — все остальные настройки: хосты VPN-нод, тарифы, лимиты, cron-расписание, уровни логирования и т.д. Какой overlay-файл подключается, определяется переменной `STAGE` (`develop` по умолчанию, либо `local`/`prod`).

Незнакомые ключи в `.env`-файлах молча игнорируются (`extra="ignore"`).

### Переменные окружения (`.env`)

| Группа | Переменные | Назначение |
|---|---|---|
| Stage | `STAGE` | `develop` \| `local` \| `prod` — выбирает `app_config.<stage>.toml` |
| Core / Bot | `BOT_TOKEN` | Токен Telegram-бота |
| Telemt | `TELEMT_SECRET_HELLO` | Секрет MTProto-прокси |
| XRay | `SOF_X_RAY_USERNAME`, `SOF_X_RAY_PASSWORD` | Учётные данные панели 3x-ui (нода `sof`) |
| Database | `DB_PASSWORD` | Пароль PostgreSQL (хост/порт/юзер/имя БД — в `app_config*.toml`, `[db]`) |
| Redis | `REDIS_PASSWORD` | Пароль Redis (хост/порт/БД — в `app_config*.toml`, `[redis]`) |
| Object Storage | `ACCESS_KEY`, `SECRET_KEY` | Доступ к S3-совместимому бакету для медиа справки |
| AI (опционально) | `SECRET_KEY_AI`, `YANDEX_FOLDER_ID` | Yandex AI Studio; актуально только при локальной разработке AI-части |
| API service | `SESSION_SECRET` | Ключ сессий админ-панели (SQLAdmin) |
| API service | `SKIP_INIT` (в `.env.example `) / `SKIP_AI_INIT` (в CI, `.github/workflows/ci.yml`) | Флаг пропуска тяжёлой инициализации AI-зависимостей при старте; имя в этих двух местах расходится — при добавлении в свой `.env` стоит свериться с тем, что реально читает код на момент использования |
| Платежи | `MERCHANT_ID`, `API_KEY` | Учётные данные платёжного шлюза (Platega) |
| Internal | `INTERNAL_API_SECRET` | Общий секрет для запросов `bot/` → `api/` (заголовок `X-Internal-Secret`); обязателен на каждом из трёх payment-вебхук-эндпоинтов `api/` |

### Настройки приложения (`app_config*.toml`)

Основные секции (см. `app_config.toml` как образец, значения — примеры):

```toml
[core]
max_configs_per_user = 10
admin_ids = [123456789]           # Telegram ID администраторов
logger_level_stdout = "INFO"

[bot]
base_site = "https://example.com/bot"
use_polling = false               # false → вебхук на base_site/webhook

[scheduler]
cron_hour = 8                     # прод: ежедневная проверка подписок в 08:00
cron_minute = 0

[pricing]
price_map = { 1 = 149, 3 = 399, 6 = 749, 12 = 1390, 7 = 0 }         # стандарт
price_map_premium = { 1 = 249, 3 = 699, 6 = 1290, 12 = 2490, 7 = 0 }
price_map_founder = { 1 = 199, 3 = 549, 6 = 1049, 12 = 1990, 7 = 0 }

[api]
url = "api"
port = 8089

[vpn.nodes.<name>]                # одна секция на каждую VPN-ноду/локацию
host = "vpn.example.com"
username = "vpn_user"
container = "amnezia-awg2"
use_local = true                  # true — бот и VPN на одном сервере
location_prefix = "XX"
flag = "🏳️"

[vpn.nodes.<name>.proxy]          # опционально — MTProto-прокси на этой ноде
prefix = "proxy-example"
container = "telemt"
port = 443

[vpn.nodes.<name>.xray]           # опционально — XRay/3x-ui панель на этой ноде
host = "vpn.example.com"
panel_prefix = "panel-xxxxx"
subscription_prefix = "sub-xxxxx"
panel_port = 5443
subscription_port = 2096
username = "admin"
# + [[vpn.nodes.<name>.xray.inbounds]] — список { port, name } на ноду

[db]
host = "postgres"
port = 5432
user = "vpn_user"
database = "vpn_boriska_db"

[redis]
host = "redis"
port = 6379
db = 0
default_expire = 43200            # секунд, 12 часов

[bucket]
bucket_name = "vpn-bot-images"
prefix = "media/"
endpoint_url = "https://storage.yandexcloud.net"

[ai]
model_name = "intfloat/multilingual-e5-small"
embedding_dim = 256
normalize = true
```

## Запуск

**Локально (без Docker)** — см. [«Быстрый старт»](#быстрый-старт). При `USE_POLLING=false` (или `use_polling = false` в toml) бот выставляет вебхук на `base_site/webhook`; при `true` — снимает вебхук и переходит на polling.

**Docker Compose** (рекомендуется для прод/staging):

```bash
# develop
docker compose -f docker-compose.develop.yml --env-file .env.dev up -d --build
docker compose -f docker-compose.develop.yml down

# prod
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
```

Через `makefile` те же команды короче (используют переменную `STAGE`, по умолчанию `develop`):

```bash
make compose-up            # STAGE=develop by default
make compose-up STAGE=prod
make compose-down
```

Compose-файлы поднимают `vpn_bot` (bot-сервис), `api` и `nginx_vpn_bot`; Postgres/Redis подключаются как внешние сервисы через Docker-сети `infrastructure_net`/`shared_net`.

## Миграции базы данных

Несмотря на то, что `alembic.ini` лежит в корне репозитория, `script_location` указывает на `api/migrations` — это единственное место, где реально хранятся ревизии.

```bash
alembic upgrade head                       # применить все миграции
alembic revision --autogenerate -m "msg"   # создать новую ревизию

# то же через make
make rev-up
make rev MSG="add new column"
make rev-down                              # откатить последнюю
```

## Тесты и качество кода

```bash
pytest -q                                          # весь набор (bot/tests + api/tests)
pytest bot/tests/unit/test_vpn_service.py           # один файл
pytest -m vpn                                       # по маркеру (см. pytest.ini)
make pytests                                        # то же через make

make coverage                                       # тесты + отчёт покрытия
# -> терминал (term-missing) + htmlcov/index.html
```

Маркеры (`pytest.ini`): `admin`, `dao`, `dialogs`, `help`, `middleware`, `subscription`, `users`, `utils`, `vpn`, `bot`, `integration`, `referrals`, `news`, `info`.

Стиль и типы — зеркалируют CI (`.github/workflows/ci.yml`) и pre-commit:

```bash
poetry run black --check .
poetry run isort --check-only --profile black .
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy .

make pre-commit      # pre-commit run --all-files
make ci-checks        # весь набор проверок + тесты одной командой
```

`ruff.toml`/`[tool.mypy]` в `pyproject.toml` исключают из проверок `*/migrations/*`, `bot/tests/`, `api/tests/` и (только для mypy) `bot/vpn/utils/`.

## Платежи

Оплата подписки картой идёт через провайдера **Platega** (`bot/payment/providers/platega.py`, интерфейс `BasePaymentProvider`). Поток:

1. `bot/subscription/` создаёт транзакцию (`api/payment`) и получает от Platega ссылку на оплату.
2. Platega шлёт результат на `POST /payment-webhook` (`bot/payment/router.py`) — подпись проверяется по заголовкам `X-MerchantId`/`X-Secret` (`PlategaProvider.verify_webhook`, сравнение constant-time).
3. `PaymentWebhookService` разбирает событие и вызывает подтверждение/отмену на `api/` (эндпоинты `api/payment/router.py` под `POST /payment/transaction/webhook/{confirm,cancel}` — защищены отдельным заголовком `X-Internal-Secret`, так как у вебхука нет Telegram-контекста пользователя).
4. При успехе продлевается подписка в БД и XRay-конфиги на всех панелях 3x-ui, начисляется реферальный бонус приглашавшему (если применимо).

Подтверждение администратором вручную (перевод не через платёжный шлюз) идёт отдельным путём — `POST /payment/transaction/admin/confirm`.

## MTProto-прокси (telemt)

Вместо socks5 используется MTProto-прокси на базе [telemt](https://github.com/An0nX/telemt-docker) (образ `whn0thacked/telemt-docker`, сервис `telemt` в `docker-compose.prod.yml`).

Подготовка конфигурации на сервере:

```bash
mkdir -p ./telemt-config
touch ./telemt-config/telemt.toml
chmod 777 ./telemt-config
chmod 666 ./telemt-config/telemt.toml

# секрет (16 байт / 32 hex-символа) — подставить в telemt.toml
openssl rand -hex 16
```

Заполните `telemt.toml` по документации upstream-репозитория и запустите через нужный `docker-compose.*.yml` — volume `./telemt-config` уже смонтирован в сервис.

Замечания по продакшну:
- Убедитесь, что контейнер имеет доступ к публичному порту прокси (обычно 443).
- Если у сервера два публичных IP и нужно обслуживать оба через один nginx — запускайте nginx в `network_mode: host` (или эквиваленте), иначе он будет видеть только один IP.

## Nginx

Примеры конфигураций для проксирования обоих FastAPI-сервисов (включая Telegram- и payment-вебхуки) — `nginx.conf` (прод) и `nginx_test.conf` (тест-стенд).

## Эксплуатационные заметки

<details>
<summary>Лимит конфигов AmneziaWG выше 256 (по умолчанию WireGuard ограничен подсетью /24)</summary>

```bash
Address = 10.8.0.1/16
# перезапуск wg
wg-quick down /opt/amnezia/awg/awg0.conf 2>/dev/null
wg-quick up /opt/amnezia/awg/awg0.conf

# очищаем старые правила
iptables -F
iptables -t nat -F

# разрешаем туннель
iptables -A INPUT -i wg0 -j ACCEPT
iptables -A OUTPUT -o wg0 -j ACCEPT
iptables -A FORWARD -i wg0 -j ACCEPT
iptables -A FORWARD -m state --state ESTABLISHED,RELATED -j ACCEPT

# FORWARD + NAT для новой подсети (интерфейсы — под ваш сервер)
iptables -A FORWARD -i wg0 -o eth0 -s 10.8.0.0/16 -j ACCEPT
iptables -A FORWARD -i wg0 -o eth1 -s 10.8.0.0/16 -j ACCEPT
iptables -t nat -A POSTROUTING -s 10.8.0.0/16 -o eth0 -j MASQUERADE
iptables -t nat -A POSTROUTING -s 10.8.0.0/16 -o eth1 -j MASQUERADE
```
</details>

<details>
<summary>3proxy — файл пользователей для прокси-сервера</summary>

`users.txt`:
```
proxy_user:CL:j88WSiGkjVdbLWxZ
```

В `3proxy.cfg` подключить его:
```
users $/usr/local/3proxy/conf/users.txt
```
</details>

<details>
<summary>Установка PyTorch (нужен для AI-части) — нестандартный индекс пакетов</summary>

```bash
poetry run pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```
</details>

## Лицензия

В репозитории нет файла `LICENSE` — лицензия формально не определена, проект по умолчанию закрытый (all rights reserved). Если планируется открыть код — добавьте `LICENSE` и обновите этот раздел.
