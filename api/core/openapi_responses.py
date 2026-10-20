"""Переиспользуемые описания OpenAPI-ответов для приватных эндпоинтов.

``AUTH_RESPONSES``/``ADMIN_RESPONSES`` документируют коды ошибок, которые
может поднять ``Depends(get_current_user)``/``Depends(check_admin_role)``
(см. ``api/core/dependencies.py``, ``api/admin/dependencies.py``) — чтобы
Swagger показывал их одинаково для всех защищённых роутов, а не только
там, где их вручную перечислили.
"""

from typing import Any

from api.core.exceptions.schema import APIErrorResponse

AUTH_RESPONSES: dict[int | str, dict[str, Any]] = {
    401: {
        "model": APIErrorResponse,
        "description": "Отсутствует или неверен заголовок X-Internal-Secret",
    },
    403: {
        "model": APIErrorResponse,
        "description": "Отсутствует заголовок X-Telegram-Id",
    },
    404: {
        "model": APIErrorResponse,
        "description": "Пользователь с указанным X-Telegram-Id не зарегистрирован",
    },
}

ADMIN_RESPONSES: dict[int | str, dict[str, Any]] = {
    **AUTH_RESPONSES,
    403: {
        "model": APIErrorResponse,
        "description": (
            "Отсутствует заголовок X-Telegram-Id, либо у пользователя "
            "нет роли admin/founder"
        ),
    },
}
