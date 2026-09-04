#!/usr/bin/env bash
set -euo pipefail

# Рабочая директория скрипта
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
CONFIG_FILE="${CONFIG_FILE:-app_config.toml}"
# ===================== LOAD ENV =====================

# Подгружаем .env и .env.local если они существуют
set -a
[ -f ".env" ] && source .env
[ -f ".env.local" ] && source .env.local
set +a

# ===================== LOAD TOML CONFIG =====================
eval "$(
python3 - <<PY
import tomllib

with open("${CONFIG_FILE}", "rb") as f:
    cfg = tomllib.load(f)
db = cfg["db"]
core = cfg["core"]

#print(f"DB_HOST={db.get('host','localhost')}")
print(f"DB_PORT={db.get('port', 5432)}")
print(f"DB_USER={db['user']}")
print(f"DB_DATABASE={db['database']}")

admins = core.get("admin_ids", [])
print("ADMIN_IDS=\"" + ",".join(map(str, admins)) + "\"")
PY
)"

# ===================== CONFIG =====================

# PostgreSQL (берётся из env)
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-user_vpn}"
DB_DATABASE="${DB_DATABASE:-vpn_boriska_db}"
DB_PASSWORD="${DB_PASSWORD:-}"

# Backup
BACKUP_DIR="${BACKUP_DIR:-./backup}"
DATE="$(date +'%Y-%m-%d_%H-%M-%S')"
BACKUP_NAME="vpn_${DATE}.backup"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}"
mkdir -p "$BACKUP_DIR"

# Yandex S3
BUCKET_NAME="${BUCKET_NAME:-vpn-bot-images}"
PREFIX="backup"
ENDPOINT_URL="${ENDPOINT_URL:-https://storage.yandexcloud.net}"
export AWS_ACCESS_KEY_ID="$ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="$SECRET_KEY"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-ru-central1}"


# Telegram
BOT_TOKEN="${BOT_TOKEN:-}"
ADMIN_IDS="${ADMIN_IDS:-}"


# ===================== FUNCTIONS =====================

notify_success() {
  curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
    -H "Content-Type: application/json" \
    -d "{
      \"chat_id\": \"${ADMIN_IDS}\",
      \"text\": \"✅ Бэкап БД и конфигов VPN-нод выполнен успешно\n\n📦 Файл БД: ${BACKUP_NAME}\n🕒 Время: ${DATE}\n\nАрхивы контейнеров:\n$1\"
    }"
}

notify_error() {
  curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
    -H "Content-Type: application/json" \
    -d "{
      \"chat_id\": \"${ADMIN_IDS}\",
      \"text\": \"❌ Ошибка бэкапа БД\n\n📦 Файл: ${BACKUP_NAME}\n🕒 Время: ${DATE}\n📄 Детали: $1\"
    }"
}

notify_containers_error() {
  curl -s -X POST "https://api.telegram.org/bot${BOT_TOKEN}/sendMessage" \
    -H "Content-Type: application/json" \
    -d "{
      \"chat_id\": \"${ADMIN_IDS}\",
      \"text\": \"❌ Ошибка бэкапа VPN-контейнеров\n\n🕒 Время: ${DATE}\n📄 Детали: $1\"
    }"
}

# ===================== LOGIC =====================

trap 'notify_error "скрипт завершился с ошибкой"' ERR

if [ -z "$DB_PASSWORD" ]; then
    echo "[ERROR] Не задан пароль PostgreSQL. Установите PG_PASSWORD в .env"
    notify_error "Не задан пароль PostgreSQL"
    exit 1
fi

export PGPASSWORD="$DB_PASSWORD"

echo "[INFO] Creating PostgreSQL backup..."
pg_dump \
  -h "${DB_HOST}" \
  -p "${DB_PORT}" \
  -U "${DB_USER}" \
  -F c \
  -f "${BACKUP_PATH}" \
  "${DB_DATABASE}"

unset PGPASSWORD


echo "[INFO] Uploading backup to Yandex S3..."
aws \
  --endpoint-url "${ENDPOINT_URL}" \
  s3 cp \
  "${BACKUP_PATH}" \
  "s3://${BUCKET_NAME}/${PREFIX}/${BACKUP_NAME}"

echo "[INFO] Cleaning up local file..."
rm -f "${BACKUP_PATH}"

unset AWS_ACCESS_KEY_ID
unset AWS_SECRET_ACCESS_KEY
unset AWS_DEFAULT_REGION

echo "[INFO] Backing up VPN container configs (Amnezia)..."
if ! CONTAINER_BACKUP_OUTPUT="$(docker exec vpn_bot python -m bot.vpn.utils.backup_containers)"; then
  notify_containers_error "не удалось создать/загрузить бэкап конфигов VPN-нод"
  exit 1
fi
echo "$CONTAINER_BACKUP_OUTPUT"

CONTAINERS_TEXT=""
while IFS= read -r line; do
  case "$line" in
    BACKUP_KEY::*)
      CONTAINERS_TEXT="${CONTAINERS_TEXT}📦 ${line#BACKUP_KEY::}\n"
      ;;
  esac
done <<< "$CONTAINER_BACKUP_OUTPUT"

notify_success "$CONTAINERS_TEXT"
echo "[INFO] Backup finished successfully"
