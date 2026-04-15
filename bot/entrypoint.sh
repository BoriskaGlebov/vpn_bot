#!/bin/bash
set -euo pipefail

echo "Выставляем корректные права на папку логов"
mkdir -p /vpn_bot/bot/logs
chown -R botuser:bot /vpn_bot/bot/logs

#echo "⚙️ Checking for Alembic migrations..."

## Проверяем наличие alembic-конфигурации
#if [ -d "bot/migrations" ] && [ -f "alembic.ini" ]; then
#    echo "📦 Alembic detected — applying migrations..."
#    alembic upgrade head
#
#    echo "🧹 Cleaning up Alembic migration files..."
#    rm -rf bot/migrations alembic.ini || true
#    echo "✅ Migrations applied and Alembic removed."
#else
#    echo "ℹ️ Alembic not found — skipping migrations."
#fi

echo "🚀 Starting bot..."
#exec su -s /bin/bash botuser -c  "python -m bot.main"
exec python -m bot.main
