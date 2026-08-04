#!/bin/bash
set -euo pipefail

mkdir -p /vpn_bot/bot/logs

echo "🚀 Starting bot..."
# Запускаем от root: боту нужен доступ к /var/run/docker.sock и к сокету
# ssh-agent, прокинутым с хоста — оба принадлежат хостовому UID/GID, не
# совпадающему с непривилегированным пользователем внутри контейнера.
exec python -m bot.main
