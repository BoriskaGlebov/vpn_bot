# --- Base image ---
FROM python:3.12-slim

# Настройки Poetry — .venv будет внутри проекта
ENV POETRY_VERSION=1.8.0 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=true \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    PATH="/vpn_bot/.venv/bin:/vpn_bot/.local/bin:$PATH"

# Создаём пользователя
RUN groupadd -r bot && \
    useradd -r -g bot -d /vpn_bot -s /bin/bash -m botuser

WORKDIR /vpn_bot

# rsync нужен entrypoint.sh для атомарной синхронизации volume с шаблонами/статикой
RUN apt-get update && \
    apt-get install -y --no-install-recommends rsync && \
    rm -rf /var/lib/apt/lists/*

# Устанавливаем Poetry
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "poetry==$POETRY_VERSION"

# Копируем декларации зависимостей
COPY --chown=botuser:bot pyproject.toml poetry.lock ./

# Устанавливаем зависимости (без dev)
RUN poetry install --without dev --no-cache

# Копируем проект целиком
COPY --chown=botuser:bot api/ api/
COPY --chown=botuser:bot pyproject.toml poetry.lock alembic.ini app_config.toml app_config.develop.toml  ./
COPY --chown=botuser:bot shared/ shared/

# Эталонная копия шаблонов вне api/templates: в docker-compose поверх
# api/templates монтируется именованный volume (чтобы шаблоны раздавал
# nginx напрямую), а Docker не обновляет уже существующий volume при
# пересборке образа. entrypoint.sh синхронизирует volume из этой копии
# при каждом старте контейнера, чтобы volume не отставал от образа.
RUN cp -a api/templates api/templates_src && \
    chown -R botuser:bot api/templates_src

# То же самое для статики sqladmin: volume в docker-compose монтируется
# только в подпапку statics (не на весь пакет sqladmin — иначе volume
# заморозил бы и сам код библиотеки на старой версии, игнорируя
# обновления sqladmin через poetry.lock). Эталонная копия — вне зоны
# volume-монтирования, синхронизируется entrypoint.sh при каждом старте.
RUN cp -a /vpn_bot/.venv/lib/python3.12/site-packages/sqladmin/statics /vpn_bot/sqladmin_statics_src && \
    chown -R botuser:bot /vpn_bot/sqladmin_statics_src

# Делаем entrypoint исполняемым
RUN chmod +x ./api/entrypoint.sh

ENTRYPOINT ["./api/entrypoint.sh"]
