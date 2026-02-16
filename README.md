# vpn_bot

Телеграм-бот для выдачи VPN-конфигураций Amnezia VPN с администрированием через Telegram и HTTP API (FastAPI). Поддерживает подписки, реферальную систему, напоминания, планировщик задач и хранение медиа (локально или S3-совместимые хранилища).

## Возможности
- Выдача новых VPN-конфигураций и управление существующими
- Управление подписками, продлениями, напоминаниями
- Реферальная программа
- Админ-функции через Telegram (клавиатуры, панели) и HTTP API
- Получение обновлений: webhook или polling
- Планировщик задач (APScheduler)
- Хранилище кэша/очередей на Redis
- Миграции БД через Alembic

## Технологии
- Python 3.11+
- Aiogram (Telegram Bot)
- FastAPI (HTTP API)
- PostgreSQL (основная БД)
- Redis (кэш, блокировки, rate-limit и т.п.)
- Alembic (миграции)
- Docker/Compose (развёртывание)
- ruff, mypy, pytest (качество кода и тесты)

## Структура проекта
Высокоуровнево:
- bot/
  - admin/, users/, subscription/, vpn/, help/ — доменные модули (enums, dao, models, services, keyboards)
  - middleware/ — промежуточные обработчики (исключения, логирование/аудит действий пользователя)
  - utils/ — вспомогательные утилиты (команды, старт/стоп бота, инициализация ролей, описание)
  - app_error/ — базовые ошибки приложения
  - database.py — инициализация БД
  - config.py — конфигурация приложения/бота
  - main.py — точка входа (FastAPI + жизненный цикл бота)
  - migrations/ — миграции Alembic
- tests/ — unit и integration тесты (pytest)
- docker-compose.*.yml — сценарии для dev/prod
- Dockerfile, entrypoint.sh, nginx*.conf — инфраструктура контейнеров

## Требования
- Python 3.11+
- PostgreSQL 14+
- Redis 6+
- (опционально) S3-совместимое хранилище для медиа (например, Yandex Object Storage)

## Установка (локально)
1) Клонировать репозиторий
```
git clone https://github.com/BoriskaGlebov/vpn_bot
cd vpn_bot
```

2) Установить зависимости
- Poetry:
```
poetry install --without dev --no-cache
```
Проект содержит pyproject.toml — зависимости можно ставить через предпочитаемый менеджер (pip/poetry).

3) Настроить переменные окружения
Создайте файл .env в корне проекта.

Пример .env:
```
# --- Telegram / Bot ---
BOT_TOKEN=your_bot_token_here
ADMIN_IDS=123456789,987654321
BASE_SITE=https://your-domain.com
USE_POLLING=True
DEBUG_FAST_API=True
RELOAD_FAST_API=True

# --- VPN backend ---
VPN_HOST=vpn.example.com
VPN_USERNAME=vpnuser
VPN_CONTAINER=amnezia-vpn
MAX_CONFIGS_PER_USER=10

# --- Logging ---
LOGGER_LEVEL_STDOUT=DEBUG
LOGGER_LEVEL_FILE=DEBUG
LOGGER_ERROR_FILE=WARNING

# --- Database (PostgreSQL) ---
DB_HOST=postgres
DB_PORT=5432
DB_USER=user
DB_PASSWORD=your_password
DB_DATABASE=your_database

# --- Redis ---
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_USER=default
REDIS_PASSWORD=your_redis_password
NUM_DB=0
DEFAULT_EXPIRE=3600

# --- S3 / Object Storage (опционально) ---
BUCKET_NAME=vpn-bot-images
PREFIX=media/
ENDPOINT_URL=https://storage.yandexcloud.net
ACCESS_KEY=your_key
SECRET_KEY=your_key
```

Ключевые переменные:
- BOT_TOKEN — токен Telegram-бота
- ADMIN_IDS — список Telegram ID администраторов (через запятую)
- BASE_SITE — базовый URL для вебхука: ${BASE_SITE}/webhook
- USE_POLLING — включить polling-режим вместо вебхука
- VPN_HOST / VPN_USERNAME / VPN_CONTAINER — параметры интеграции с Amnezia VPN
- MAX_CONFIGS_PER_USER — лимит конфигов для пользователя
- LOGGER_LEVEL_* — уровни логирования
- DB_* — подключение к PostgreSQL
- REDIS_* / NUM_DB / DEFAULT_EXPIRE — параметры Redis
- BUCKET_NAME / PREFIX / ENDPOINT_URL / ACCESS_KEY / SECRET_KEY — доступ к S3

Примечания:
- По умолчанию DB_HOST=postgres, REDIS_HOST=redis (актуально для Docker). Для локального запуска без контейнеров поменяйте на localhost.

## Инициализация БД
Запустите миграции Alembic:
```
alembic upgrade head
```
Конфиг Alembic находится в alembic.ini, скрипты — в bot/migrations/versions.

## Запуск

- Локально:
```
python bot/main.py
```
По умолчанию поднимется FastAPI и инициализируется бот. Включённый USE_POLLING удалит вебхук и запустит polling. Если USE_POLLING=False — будет установлен вебхук на BASE_SITE/webhook.

Документация API (по умолчанию):
- http://localhost:8088/bot/docs

- Docker Compose (рекомендовано):
Доступны:
- docker-compose.develop.yml — режим разработки
- docker-compose.prod.yml — продакшн
- docker-compose.common.yml — общие сервисы

Пример (dev):
```
docker compose -f docker-compose.develop.yml up -d --build
```
Остановка:
```
docker compose -f docker-compose.develop.yml down
```

## Компоненты доменов
- bot/vpn — интеграция с Amnezia VPN (utils/amnezia_*.py), модели/DAO/сервисы
- bot/subscription — подписки, биллинг, планировщик (utils/scheduler_cron.py)
- bot/referrals — реферальная программа
- bot/users — пользователи, роли, клавиатуры
- bot/admin — админ-панели/клавиатуры
- bot/help — справка/гайды для устройств (android/iphone/pc/tv)

## Middleware
- bot/middleware/exception_middleware.py — обработка исключений
- bot/middleware/user_action_middleware.py — аудит/логирование действий

## Скрипты/утилиты
- bot/utils/start_stop_bot.py — запуск/остановка бота
- bot/utils/init_default_roles.py — инициализация ролей
- bot/utils/commands.py — команды бота
- bot/utils/set_description_file.py — описание бота

## Тестирование
Конфигурация pytest — pytest.ini. Тесты находятся в tests/.

Запуск:
```
pytest -q
```



```bash
  # перезапуск wg
  wg-quick down /opt/amnezia/awg/wg0.conf 2>/dev/null
  wg-quick up /opt/amnezia/awg/wg0.conf
  # очищаем старые правила
  iptables -F
  iptables -t nat -F

  # разрешаем туннель
  iptables -A INPUT -i wg0 -j ACCEPT
  iptables -A OUTPUT -o wg0 -j ACCEPT
  iptables -A FORWARD -i wg0 -j ACCEPT
  iptables -A FORWARD -m state --state ESTABLISHED,RELATED -j ACCEPT

  # FORWARD + NAT для новой подсети
  iptables -A FORWARD -i wg0 -o eth0 -s 10.8.0.0/16 -j ACCEPT
  iptables -A FORWARD -i wg0 -o eth1 -s 10.8.0.0/16 -j ACCEPT
  iptables -t nat -A POSTROUTING -s 10.8.0.0/16 -o eth0 -j MASQUERADE
  iptables -t nat -A POSTROUTING -s 10.8.0.0/16 -o eth1 -j MASQUERADE

```
Стиль кода: ruff, mypy (pyproject.toml, ruff.toml). Pre-commit хуки — .pre-commit-config.yaml.

## Деплой Nginx
В репозитории есть примеры конфигураций nginx.conf и nginx_test.conf для проксирования FastAPI/вебхука.

## Лицензия
MIT
