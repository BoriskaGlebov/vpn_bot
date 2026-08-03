#!/bin/bash
set -euo pipefail

echo "Выставляем корректные права на папку логов"
mkdir -p /vpn_bot/api/logs
chown -R botuser:bot /vpn_bot/api/logs

echo "🔄 Синхронизация шаблонов в volume из образа..."
rsync -a --delete --delay-updates /vpn_bot/api/templates_src/ /vpn_bot/api/templates/
chown -R botuser:bot /vpn_bot/api/templates

echo "🔄 Синхронизация статики sqladmin в volume из образа..."
SQLADMIN_STATICS=/vpn_bot/.venv/lib/python3.12/site-packages/sqladmin/statics
rsync -a --delete --delay-updates /vpn_bot/sqladmin_statics_src/ "$SQLADMIN_STATICS/"
chown -R botuser:bot "$SQLADMIN_STATICS"

echo "⚙️ Checking for Alembic migrations..."

# Проверяем наличие alembic-конфигурации
if [ -d "api/migrations" ] && [ -f "alembic.ini" ]; then
    echo "📦 Alembic detected — applying migrations..."
    alembic upgrade head
#
    echo "🧹 Cleaning up Alembic migration files..."
    rm -rf api/migrations alembic.ini || true
    echo "✅ Migrations applied and Alembic removed."
else
    echo "ℹ️ Alembic not found — skipping migrations."
fi

echo "🚀 Starting api..."
exec su -s /bin/bash botuser -c  "python -m api.main"
#exec python -m api.main
