# vpn_bot

Бот для раздачи конфигураций Amnezia VPN с администрированием через Telegram и HTTP API (FastAPI).

## Возможности
- Выдача новых VPN-конфигураций пользователям
- Напоминание о действующих/истекающих конфигурациях
- Управление подписками и оплатами
- Админ-функции (через Telegram)
- Webhook или polling режим получения обновлений
- Планировщик задач (APScheduler)

## Требования
- Python 3.11+
- PostgreSQL
- Redis
- (Опционально) S3-совместимое хранилище для медиа (например, Yandex Object Storage)

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/yourusername/vpn_bot.git
cd vpn_bot
```

2. Установите зависимости (через Poetry):
```bash
poetry install
```

## Настройка переменных окружения
Перед запуском создайте файл `.env` в корне проекта.

### Пример файла .env
```dotenv
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

Описание ключевых переменных:
- BOT_TOKEN — токен Telegram-бота
- ADMIN_IDS — запятая-разделенный список Telegram ID администраторов (например: `123,456`)
- BASE_SITE — базовый URL сервера (используется для webhooks). Вебхук будет установлен на `${BASE_SITE}/webhook`
- USE_POLLING — переключатель между polling и webhook
- VPN_HOST / VPN_USERNAME / VPN_CONTAINER — параметры для интеграции с Amnezia VPN
- MAX_CONFIGS_PER_USER — лимит конфигов на пользователя
- LOGGER_LEVEL_* — уровни логирования для stdout/файлов
- DB_* — параметры подключения к PostgreSQL
- REDIS_* / NUM_DB / DEFAULT_EXPIRE — параметры подключения к Redis
- BUCKET_NAME / PREFIX / ENDPOINT_URL / ACCESS_KEY / SECRET_KEY — доступ к S3-совместимому хранилищу

Примечания:
- В коде заложены значения по умолчанию: `DB_HOST=postgres`, `REDIS_HOST=redis`. Переопределите их в `.env`, если запускаете локально без Docker.
- ADMIN_IDS может быть строкой со списком через запятую или коллекцией. Внутренний парсер преобразует значения к множеству целых чисел.

## Запуск

### Локально (через Python)
```bash
python bot/main.py
```
Приложение поднимет FastAPI с жизненным циклом бота. Если включен polling, вебхук будет удалён и запустится обработка обновлений через polling. Если polling выключен, будет установлен вебхук на `BASE_SITE/webhook`.

Документация API: http://localhost:8088/bot/docs (по умолчанию, если запускаете локально и не меняли порт).

### Docker / Docker Compose (рекомендовано)
В репозитории есть несколько compose-файлов:
- `docker-compose.develop.yml` — режим разработки
- `docker-compose.prod.yml` — продакшн-конфигурация
- `docker-compose.common.yml` — общие сервисы

Пример запуска (разработка):
```bash
docker compose -f docker-compose.develop.yml up -d --build
```

Остановить:
```bash
docker compose -f docker-compose.develop.yml down
```

## Структура проекта

- `bot/` — основной код бота
  - `admin/`, `users/`, `subscription/`, `vpn/`, `help/` — доменные модули (роутеры, сервисы, клавиатуры)
  - `middleware/` — промежуточные обработчики (логирование, обработка исключений)
  - `utils/` — вспомогательные скрипты (инициализация ролей, команды)
  - `database.py` — конфигурация БД
  - `config.py` — настройки приложения, логирование, инициализация бота/dispatcher
  - `main.py` — FastAPI-приложение и lifecycle бота
  - `logs/` — файлы логов
  - `migrations/` — миграции Alembic
- `tests/` — unit и integration тесты

## Вебхук
- Эндпоинт: `POST /webhook`
- Ожидает JSON-обновления от Telegram, валидирует и передаёт в Aiogram dispatcher.

## Разработка
- Стиль кода: ruff + mypy (конфиги в `ruff.toml`, `pyproject.toml`, `pytest.ini`)
- Тесты: `pytest`

Запуск тестов:
```bash
pytest -q
```

## Лицензия
MIT
