# vpn_bot

Telegram-бот и набор сервисов для выдачи VPN-доступов и управления подписками.

## Проект состоит из двух FastAPI-приложений:
- **Bot service** (`bot/`) — Telegram-бот на **aiogram 3**, принимает webhook/polling и управляет пользовательскими сценариями.
- **API service** (`api/`) — внутренний HTTP API + админка (**SQLAdmin**) для управления пользователями/подписками/VPN-конфигами.

## Поддерживаются:
- выдача конфигураций (Amnezia/WireGuard) и лимиты на пользователя
- подписки/тарифы, триал, напоминания и планировщик задач
- реферальная система
- прокси (MTProto через **telemt**) и отдельные настройки для тестового прокси
- интеграция с **XRay / 3x-ui** (панель + подписки)
- хранение медиа локально или в S3-совместимом Object Storage
- (опционально) AI/LLM-интеграция (Yandex AI Studio + LangChain + pgvector)

## Технологии
- Python 3.11+
- Aiogram (Telegram Bot)
- FastAPI (HTTP API)
- PostgreSQL (основная БД)
- Redis (кэш, блокировки, rate-limit и т.п.)
- Alembic (миграции)
- Docker/Compose (развёртывание)
- ruff, mypy, pytest (качество кода и тесты)


## Сервисы и порты

По умолчанию:
- Bot service: `http://localhost:8088/bot`
  - Swagger: `http://localhost:8088/bot/docs`
  - Health: `http://localhost:8088/bot/health`
  - Webhook endpoint: `POST /bot/webhook`
- API service: `http://localhost:8089/api`
  - Swagger: `http://localhost:8089/api/docs`
  - Health: `http://localhost:8089/api/health`
  - Admin UI: поднимается внутри API (SQLAdmin), путь зависит от роутера `api/admin/router.py`

---

## Структура репозитория

Высокоуровнево:
- `bot/` — Telegram bot + FastAPI (webhook endpoint)
- `api/` — внутренний API + SQLAdmin
- `shared/` — общие компоненты (если используются)
- `ai_service/` — AI/LLM компоненты (если используются)
- `telemt-config/` — конфигурация MTProto-прокси (telemt)
- `docker-compose.*.yml` — сценарии запуска (develop/local/prod/common)
- `nginx.conf`, `nginx_test.conf` — примеры конфигураций nginx

---

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

3) Настроить переменные окружения (.env)
Создайте файл .env в корне проекта. Переменные читаются из bot/.env и bot/.env.local (второй перекрывает первый).
В репозитории обновлён файл .env.example: в нём добавлены новые имена переменных и порты, необходимые для корректной работы сервиса. Обязательно откройте .env.example и скорректируйте свой .env в соответствии с ним — особенно блоки, связанные с прокси/MTProto, портами и префиксами поддоменов.
## Переменные окружения

Актуальный список и комментарии — в файле **`.env.example `** (обратите внимание: имя файла в репозитории содержит пробел в конце).

Ниже — ключевые группы переменных.

### Core / Bot
- `STAGE` — окружение (`develop`/`local`/`prod`)
- `BOT_TOKEN` — токен Telegram-бота
- `ADMIN_IDS` — список Telegram ID админов через запятую
- `BASE_SITE` — публичный базовый URL (нужен для webhook)
- `USE_POLLING` — `True` для polling, `False` для webhook
- `USE_LOCAL` — если бот и VPN на одном сервере
- `COMMON_TIMEOUT` — таймаут внешних запросов
- `MAX_CONFIGS_PER_USER` — лимит конфигов на пользователя

### Тарифы
- `PRICE_MAP`, `PRICE_MAP_PREMIUM`, `PRICE_MAP_FOUNDER` — JSON-словари цен (ключи: `1,3,6,12,7` месяцев)

### Bot/API debug & logging
- `DEBUG_FAST_API`, `RELOAD_FAST_API`
- `LOGGER_LEVEL_STDOUT`, `LOGGER_LEVEL_FILE`, `LOGGER_ERROR_FILE`

### VPN (Amnezia/WireGuard)
- `VPN_HOST`, `VPN_USERNAME`, `VPN_CONTAINER`

### Proxy (telemt)
- `VPN_PROXY` — имя контейнера прокси (в compose по умолчанию `telemt`)
- `PROXY_PREFIX` — префикс поддомена/маршрутизации для прокси
- `PROXY_PORT` — порт прокси (часто 443/8443)
- `TELEMT_SECRET_HELLO` — секрет для telemt

### Test proxy
- `VPN_TEST_HOST`, `VPN_TEST_USERNAME`, `PROXY_TEST_PREFIX`

### XRay / 3x-ui
- `X_RAY_HOST`
- `X_RAY_PANEL_PREFIX`, `X_RAY_SUBSCRIPTION_PREFIX`
- `X_RAY_PANEL_PORT`, `X_RAY_SUBSCRIPTION_PORT`
- `X_RAY_USERNAME`, `X_RAY_PASSWORD`
- `INBOUNDS` — JSON со списком inbound’ов (порт + имя)

### Database (PostgreSQL)
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_DATABASE`

### Redis
- `REDIS_HOST`, `REDIS_PORT`, `REDIS_USER`, `REDIS_PASSWORD`
- `NUM_DB`, `DEFAULT_EXPIRE`

### Object Storage (S3)
- `BUCKET_NAME`, `PREFIX`, `ENDPOINT_URL`, `ACCESS_KEY`, `SECRET_KEY`

### AI (опционально)
- `SECRET_KEY_AI`, `YANDEX_FOLDER_ID`
- `MODEL_LLM_NAME`, `EMBEDDING_DIM`, `NORMALIZE`
- `SKIP_AI_INIT` — пропуск тяжёлой инициализации (полезно в prod/CI)

### API service
- `SESSION_SECRET` — ключ для сессий/авторизации админки
- `API_URL`, `API_PORT` — адрес API сервиса для внутренних вызовов

---

## MTProto-прокс�� (telemt)

В `docker-compose.prod.yml` присутствует сервис `telemt` (образ `whn0thacked/telemt-docker`).
Конфигурация монтируется из каталога `./telemt-config`.

Подготовка:
```bash
mkdir -p ./telemt-config
touch ./telemt-config/telemt.toml
chmod 777 ./telemt-config
chmod 666 ./telemt-config/telemt.toml

# секрет (16 байт / 32 hex символа)
openssl rand -hex 16
```

Примечания
- По умолчанию DB_HOST=postgres и REDIS_HOST=redis (актуально для Docker). Для локального запуска без контейнеров поменяйте на localhost.
- Переменные S3 обязательны только если вы хотите подгружать медиа-файлы справки из бакета. Иначе модуль справки не сможет получать картинки из S3.
- Переменные читаются через pydantic-settings; любые лишние значения в .env игнорируются.

## MTProto-прокси (telemt)
Вместо socks5 в проект добавлена поддержка MTProto-прокси. Для простого развёртывания можно использовать репозиторий telemt-docker: https://github.com/An0nX/telemt-docker

Краткая инструкция по подготовке конфигурации (локально на сервере):

1) Создать каталог для конфигурации и пустой toml:
```
mkdir ./telemt-config
# Create and edit your config inside
touch ./telemt-config/telemt.toml
```

2) Выставить права, чтобы non-root пользователь контейнера мог изменять конфиг:
```
chmod 777 ./telemt-config
chmod 666 ./telemt-config/telemt.toml
```

3) В репозитории telemt-docker используется docker-compose и кастомный telemt.toml — поместите ваш telemt.toml в созданный каталог и запустите через docker compose согласно инструкции в upstream-репозитории. Docker-compose файл подхватит каталог и применит конфигурацию.

4) Для генерации первичного ключа (секрет, 16 байт / 32 символа в hex) можно использовать openssl:
```
openssl rand -hex 16
```
Сгенерированную строку подставьте в конфиг telemt.toml согласно документации telemt-docker.

Замечания по продакшну:
- Используйте docker-compose.prod.yml или ваш production compose, убедитесь, что volume ./telemt-config смонтирован в контейнер и что контейнер имеет доступ к привязанным портам (обычно 443).
- Если сервер имеет два публичных IP, и вам нужно обслуживать оба IP адреса через nginx и прокси, запускайте nginx в network_mode: host (или эквивалентную настройку), чтобы nginx видел оба IP и мог корректно отвечать/перенаправлять трафик.

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


## Важнаые настройки AmneziaWG, которые позволяют генерировать больше конфиг файлов, по умолчанию только 256.
```bash
  Address = 10.8.0.1/16
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
На прокси надо создать файл users.txt
```aiignore
proxy_user:CL:j88WSiGkjVdbLWxZ

```
Тае же надо отредактировать файл 3proxy.cfg
```aiignore
users $/usr/local/3proxy/conf/users.txt

```
Там нестандартная утснаовка Pytorch
```aiignore
  poetry run pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```
Стиль кода: ruff, mypy (pyproject.toml, ruff.toml). Pre-commit хуки — .pre-commit-config.yaml.

## Деплой Nginx
В репозитории есть примеры конфигураций nginx.conf и nginx_test.conf для проксирования FastAPI/вебхука.

## Лицензия
MIT
