from loguru import logger

from bot.integrations.api_client import APIClient
from shared.enums.admin_enum import RoleEnum
from shared.schemas.admin import SChangeRole, SExtendSubscription
from shared.schemas.users import SUserOut


class AdminAPIAdapter:
    """Адаптер для взаимодействия с Admin API.

    Инкапсулирует HTTP-вызовы к backend-сервису и возвращает
    валидированные Pydantic-схемы.

    Attributes
        _client (APIClient): HTTP клиент для выполнения запросов.

    """

    def __init__(self, client: APIClient) -> None:
        """Инициализирует адаптер.

        Args:
            client (APIClient): Экземпляр HTTP клиента.

        """
        self._client = client

    async def get_user_by_telegram_id(self, telegram_id: int) -> SUserOut:
        """Получает пользователя по Telegram ID.

        Args:
            telegram_id (int): Уникальный идентификатор пользователя.

        Returns
            SUserOut: Данные пользователя.

        Raises
            APIClientHTTPError: Если API вернул ошибку (например, 404).
            APIClientConnectionError: Если возникла ошибка соединения.
            APIClientError: При ошибке парсинга ответа.

        """
        logger.debug(
            "Запрос пользователя telegram_id={}",
            telegram_id,
        )

        data: dict[str, object] = await self._client.get(f"/admin/users/{telegram_id}")

        user = SUserOut.model_validate(data)

        logger.debug(
            "Получен пользователь telegram_id={} role={}",
            telegram_id,
            user.role,
        )

        return user

    async def get_users(self, filter_type: RoleEnum = RoleEnum.USER) -> list[SUserOut]:
        """Получает список пользователей по фильтру ролей.

        Args:
            filter_type (RoleEnum, optional): Тип фильтра пользователей.
                По умолчанию RoleEnum.USER.

        Returns
            list[SUserOut]: Список пользователей.

        Raises
            APIClientHTTPError: При ошибке HTTP.
            APIClientConnectionError: При проблемах с сетью.
            APIClientError: При некорректном ответе API.

        """
        logger.debug(
            "Запрос списка пользователей filter_type={}",
            filter_type.value,
        )

        data = await self._client.get(
            "/admin/users",
            params={"filter_type": filter_type.value},
        )

        users = [SUserOut.model_validate(item) for item in data]

        logger.debug(
            "Получен список пользователей filter_type={} count={}",
            filter_type.value,
            len(users),
        )

        return users

    async def change_user_role(self, payload: SChangeRole) -> SUserOut:
        """Изменяет роль пользователя.

        Args:
            payload (SChangeRole): Данные для изменения роли.

        Returns
            SUserOut: Обновлённые данные пользователя.

        Raises
            APIClientHTTPError: При ошибке HTTP.
            APIClientConnectionError: При проблемах с соединением.
            APIClientError: При некорректном JSON ответе.

        """
        logger.info(
            "Смена роли telegram_id={} role={}",
            payload.telegram_id,
            payload.role_name,
        )

        data: dict[str, object]
        status_code: int

        data, status_code = await self._client.patch(
            "/admin/users/role",
            json=payload.model_dump(),
        )

        user = SUserOut.model_validate(data)

        logger.success(
            "Роль изменена telegram_id={} new_role={}",
            payload.telegram_id,
            user.role,
        )

        return user

    async def extend_subscription(self, payload: SExtendSubscription) -> SUserOut:
        """Продлевает подписку пользователя.

        Args:
            payload (SExtendSubscription): Данные продления подписки.

        Returns
            SUserOut: Обновлённый пользователь.

        Raises
            APIClientHTTPError: При ошибке API.
            APIClientConnectionError: При ошибке сети.
            APIClientError: При некорректном ответе.

        """
        logger.info(
            "Продление подписки telegram_id={} months={}",
            payload.telegram_id,
            payload.months,
        )

        data: dict[str, object]
        status_code: int

        data, status_code = await self._client.patch(
            "/admin/users/subscription",
            json=payload.model_dump(),
        )

        user = SUserOut.model_validate(data)

        logger.success(
            "Подписка продлена telegram_id={} months={}",
            payload.telegram_id,
            payload.months,
        )

        return user
