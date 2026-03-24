from fastapi import Request
from fastapi.responses import JSONResponse
from loguru import logger
from starlette import status

from api.app_error.base_error import (
    ActiveSubscriptionExistsError,
    SubscriptionNotFoundError,
    TrialAlreadyUsedError,
    UserNotFoundError,
)


async def user_not_found_handler(
    request: Request, exc: UserNotFoundError
) -> JSONResponse:
    """Обрабатывает ошибку отсутствия пользователя.

    Перехватывает исключение UserNotFoundError и преобразует его
    в HTTP 404 ответ с человекочитаемым сообщением.

    Args:
        request (Request): HTTP запрос FastAPI.
        exc (UserNotFoundError): Исключение отсутствия пользователя.

    Returns
        JSONResponse: HTTP 404 ответ с описанием ошибки.

    """
    logger.warning(
        "UserNotFoundError: telegram_id={} path={}",
        exc.tg_id,
        request.url.path,
    )

    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "detail": f"Пользователь с telegram_id={exc.tg_id} не найден",
        },
    )


async def subscription_not_found_handler(
    request: Request,
    exc: SubscriptionNotFoundError,
) -> JSONResponse:
    """Обрабатывает отсутствие подписки у пользователя.

    Перехватывает исключение SubscriptionNotFoundError и возвращает
    HTTP 404 ответ с описанием отсутствующей подписки.

    Args:
        request (Request): HTTP запрос FastAPI.
        exc (SubscriptionNotFoundError): Исключение отсутствия подписки.

    Returns
        JSONResponse: HTTP 404 ответ.

    """
    logger.warning(
        "SubscriptionNotFoundError: user_id={} path={}",
        exc.user_id,
        request.url.path,
    )

    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "detail": f"У пользователя user_id={exc.user_id} не найдена подписка",
        },
    )


async def active_subscription_exists_handler(
    request: Request,
    exc: ActiveSubscriptionExistsError,
) -> JSONResponse:
    """Обрабатывает попытку создать активную подписку при уже существующей.

    Возвращает HTTP 409 Conflict.

    Args:
        request: входящий HTTP запрос FastAPI.
        exc: исключение ActiveSubscriptionExistsError.

    Returns
        JSONResponse: HTTP 409 ответ.

    """
    logger.warning(
        "ActiveSubscriptionExistsError: path={}",
        request.url.path,
    )

    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": str(exc),
        },
    )


async def trial_already_used_handler(
    request: Request,
    exc: TrialAlreadyUsedError,
) -> JSONResponse:
    """Обрабатывает повторное использование пробного периода.

    Возвращает HTTP 409 Conflict, так как это состояние бизнес-конфликта.

    Args:
        request: входящий HTTP запрос FastAPI.
        exc: исключение TrialAlreadyUsedError.

    Returns
        JSONResponse: HTTP 409 ответ с описанием ошибки.

    """
    logger.warning(
        "TrialAlreadyUsedError: path={}",
        request.url.path,
    )

    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "detail": str(exc),
        },
    )
