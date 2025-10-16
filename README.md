# vpn_bot

Бот для раздачи конфигов Amnezia VPN.

## Установка

1. Клонируйте репозиторий:# vpn_bot
Бот, который будет раздавать конфиги для Amnezia VPN
```bash
   git clone https://github.com/yourusername/vpn_bot.git cd vpn_bot
```
2. Установите зависимости:
```bash
   poetry install
```
## Настройка переменных окружения

Перед запуском создайте файл `.env` в корне проекта.
## Пример файла .env

```dotenv
BOT_TOKEN=your_bot_token_here
ADMIN_IDS='[123456789]'
BASE_SITE=https://your-domain.com
DEBUG_FAST_API=True
RELOAD_FAST_API=True

LOGGER_LEVEL_STDOUT=DEBUG
LOGGER_LEVEL_FILE=DEBUG
LOGGER_ERROR_FILE=WARNING

DB_HOST=localhost
DB_PORT=5432
DB_USER=user
DB_PASSWORD=your_password
DB_DATABASE=your_database

REDIS_PASSWORD=your_redis_password

USE_POLLING=True
```
Описание переменных
- BOT_TOKEN — токен Telegram-бота.
- ADMIN_IDS — список Telegram ID администраторов в формате строки списка.
- BASE_SITE — базовый URL сайта (например, для webhook).
- DEBUG_FAST_API — включить режим отладки FastAPI.
- RELOAD_FAST_API — авто-перезапуск FastAPI при изменениях.
- LOGGER_LEVEL_STDOUT — уровень логирования для stdout.
- LOGGER_LEVEL_FILE — уровень логирования для файла.
- LOGGER_ERROR_FILE — уровень логирования для файла ошибок.
- DB_HOST — адрес сервера базы данных.
- DB_PORT — порт базы данных.
- DB_USER — пользователь базы данных.
- DB_PASSWORD — пароль пользователя базы данных.
- DB_DATABASE — имя базы данных.
- REDIS_PASSWORD — пароль для Redis.
- USE_POLLING — использовать polling или webhook


## Запуск
```bash
python bot/main.py
```
## Структура проекта

- `bot/` — основной код бота
- `utils/` — вспомогательные скрипты
- `dialogs/` — тексты и сообщения для диалогов
- `logs/` — логи работы бота
- `migrations/` — миграции базы данных

## Лицензия

MIT
