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

# Устанавливаем системные зависимости + docker CLI
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg \
        lsb-release \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker.gpg \
    && echo \
        "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker.gpg] \
        https://download.docker.com/linux/debian \
        $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-cli \
    && rm -rf /var/lib/apt/lists/*



# Устанавливаем Poetry
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir "poetry==$POETRY_VERSION"

# Копируем декларации зависимостей
COPY --chown=botuser:bot pyproject.toml poetry.lock ./

# Устанавливаем зависимости (без dev)
RUN poetry install --without dev --no-cache

# Копируем проект целиком
COPY --chown=botuser:bot . .

# Делаем entrypoint исполняемым
RUN chmod +x ./entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
