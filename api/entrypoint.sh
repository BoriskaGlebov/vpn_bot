#!/bin/bash
set -euo pipefail

echo "Выставляем корректные права на папку логов"
mkdir -p /vpn_bot/api/logs
chown -R botuser:bot /vpn_bot/api/logs

echo "⚙️ Checking for Alembic migrations..."

# Проверяем наличие alembic-конфигурации
if [ -d "api/migrations" ] && [ -f "alembic.ini" ]; then
    echo "📦 Alembic detected — applying migrations..."
    alembic upgrade head

    echo "🧹 Cleaning up Alembic migration files..."
    rm -rf api/migrations alembic.ini || true
    echo "✅ Migrations applied and Alembic removed."
else
    echo "ℹ️ Alembic not found — skipping migrations."
fi

echo "🚀 Starting api..."
exec su -s /bin/bash botuser -c  "python -m api.main"
#exec python -m api.main
