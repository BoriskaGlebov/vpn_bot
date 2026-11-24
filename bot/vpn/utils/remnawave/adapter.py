from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from loguru import logger

from bot.app_error.api_error import APIClientConnectionError, APIClientHTTPError
from bot.integrations.api_client import APIClient
from bot.vpn.utils.remnawave.exceptions import (
    RemnawaveAuthError,
    RemnawaveError,
    RemnawaveInvalidExpiryError,
    RemnawaveRequestError,
    RemnawaveUserNotFoundError,
)
from bot.vpn.utils.remnawave.schemas import (
    RemnawaveUserCreate,
    RemnawaveUserEnvelope,
    RemnawaveUserResponse,
    RemnawaveUsersStreamEnvelope,
    RemnawaveUserUpdate,
)


class RemnawaveAdapter:
    """Адаптер для взаимодействия с панелью Remnawave.

    Инкапсулирует HTTP-взаимодействие с API панели (авторизация по
    Bearer-токену, без cookie-сессии в отличие от `ThreeXUIAdapter`) и
    предоставляет высокоуровневые операции управления пользователями.

    Пользователь на панели идентифицируется числовым `id` — начиная с
    v3.x панели у пользователей нет поля `uuid` (см. `UsersSchema` в
    `remnawave/backend`), только `id`/`shortUuid`.

    Attributes
        api_client: HTTP-клиент для работы с API панели.
        squads: Наборы squad-идентификаторов панели по ключу уровня подписки.
        tier_map: Соответствие значения подписки (`sub_type`) ключу в `squads`.
        prefix: Базовый префикс API панели (например, "/api").

    """

    UNLIMITED_EXPIRE_AT = datetime(2099, 12, 31, tzinfo=UTC)

    def __init__(
        self,
        api_client: APIClient,
        token: str,
        squads: dict[str, list[UUID]],
        tier_map: dict[str, str],
        prefix: str = "/api",
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Инициализирует адаптер Remnawave.

        Args:
            api_client: HTTP-клиент для взаимодействия с API панели.
            token: Bearer-токен для авторизации запросов.
            squads: Наборы squad-идентификаторов панели по ключу уровня
                подписки.
            tier_map: Соответствие значения подписки (`sub_type`) ключу
                в `squads`.
            prefix: Префикс API панели.
            extra_headers: Дополнительные заголовки, добавляемые к каждому
                запросу вместе с `Authorization`. Нужны, когда перед
                панелью стоит forward-auth reverse-proxy (TinyAuth и
                подобные) — такой proxy перехватывает запрос и уводит на
                страницу логина раньше, чем Bearer-токен Remnawave успевает
                сработать, если не передать его собственный байпас-заголовок
                (например, `X-Api-Key`).

        """
        self.api_client = api_client
        self._token = token
        self.squads = squads
        self.tier_map = tier_map
        self.prefix = prefix
        self._extra_headers = extra_headers or {}

    def _squads_for_tier(self, sub_type: str) -> list[UUID]:
        """Возвращает squad-идентификаторы, соответствующие уровню подписки.

        Args:
            sub_type: Значение уровня подписки (ключ в `tier_map`).

        Returns
            list[UUID]: Squad-идентификаторы панели для этого уровня.

        Raises
            RemnawaveError: Если `sub_type` не замаплен в `tier_map`, либо
                `tier_map` ссылается на отсутствующий в `squads` ключ.

        """
        group = self.tier_map.get(sub_type)
        if group is None or group not in self.squads:
            raise RemnawaveError(
                message=f"Неизвестный уровень подписки Remnawave: {sub_type}",
                details={"sub_type": sub_type},
            )
        return self.squads[group]

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], int]:
        """Выполняет запрос к панели с Bearer-авторизацией и обработкой ошибок.

        Args:
            method: HTTP метод ("GET"/"POST"/"PATCH"/"DELETE").
            path: Путь запроса (с учётом `prefix`).

        Returns
            tuple[dict[str, Any], int]: Тело ответа и HTTP статус-код.

        Raises
            RemnawaveAuthError: Панель отклонила Bearer-токен (401/403).
            RemnawaveUserNotFoundError: Пользователь не найден (404).
            RemnawaveRequestError: Прочая ошибка HTTP или соединения.

        """
        headers = {
            **self._extra_headers,
            **kwargs.pop("headers", {}),
            "Authorization": f"Bearer {self._token}",
        }
        call = getattr(self.api_client, method.lower())
        try:
            return await call(path, headers=headers, **kwargs)
        except APIClientHTTPError as exc:
            if exc.status_code in (401, 403):
                raise RemnawaveAuthError(reason=exc.error.message) from exc
            if exc.status_code == 404:
                raise RemnawaveUserNotFoundError(
                    identifier=path.rsplit("/", 1)[-1]
                ) from exc
            raise RemnawaveRequestError(
                action=f"{method} {path}",
                reason=exc.error.message,
                status_code=exc.status_code,
            ) from exc
        except APIClientConnectionError as exc:
            raise RemnawaveRequestError(
                action=f"{method} {path}", reason=str(exc), status_code=502
            ) from exc

    async def _get_user_by_tg_id(self, tg_id: int) -> RemnawaveUserResponse | None:
        """Находит пользователя панели по Telegram ID.

        Панель не отдаёт 404 для фильтра без совпадений — `GET
        /users/stream` всегда отвечает 200 с (возможно пустым) списком,
        поэтому "не найден" определяется по пустому `users`, а не по
        перехвату `RemnawaveUserNotFoundError`.

        Args:
            tg_id: Telegram ID пользователя.

        Returns
            RemnawaveUserResponse | None: Данные пользователя, либо `None`,
                если пользователь не найден.

        """
        data, _ = await self._request(
            "GET",
            f"{self.prefix}/users/stream",
            params={"telegramId": tg_id, "size": 1},
        )
        users = RemnawaveUsersStreamEnvelope.model_validate(data).response.users
        return users[0] if users else None

    async def _get_user_by_id(self, user_id: int) -> RemnawaveUserResponse | None:
        """Находит пользователя панели по его числовому `id`.

        Args:
            user_id: Идентификатор пользователя на панели.

        Returns
            RemnawaveUserResponse | None: Данные пользователя, либо `None`,
                если пользователь не найден.

        """
        try:
            data, _ = await self._request("GET", f"{self.prefix}/users/{user_id}")
        except RemnawaveUserNotFoundError:
            return None
        return RemnawaveUserEnvelope.model_validate(data).response

    async def _create_user(self, payload: RemnawaveUserCreate) -> RemnawaveUserResponse:
        """Создаёт пользователя на панели.

        Args:
            payload: Тело запроса `POST /users`.

        Returns
            RemnawaveUserResponse: Созданный пользователь.

        """
        data, _ = await self._request(
            "POST",
            f"{self.prefix}/users",
            json=payload.model_dump(mode="json", by_alias=True),
        )
        return RemnawaveUserEnvelope.model_validate(data).response

    async def _patch_user(self, payload: RemnawaveUserUpdate) -> RemnawaveUserResponse:
        """Обновляет пользователя на панели.

        Args:
            payload: Тело запроса `PATCH /users` — поля, равные `None`,
                в запрос не попадают (не трогают текущее значение на панели).

        Returns
            RemnawaveUserResponse: Обновлённый пользователь.

        """
        data, _ = await self._request(
            "PATCH",
            f"{self.prefix}/users",
            json=payload.model_dump(mode="json", by_alias=True, exclude_none=True),
        )
        return RemnawaveUserEnvelope.model_validate(data).response

    async def add_new_config(
        self,
        tg_id: int,
        expires_at: datetime | None,
        sub_type: str,
        device_limit: int,
    ) -> tuple[dict[str, list[str]], str]:
        """Выдаёт пользователю доступ на панели Remnawave.

        Если пользователь с данным `tg_id` уже существует на панели —
        обновляет его (`PATCH`), иначе создаёт нового (`POST`).

        Args:
            tg_id: Telegram ID пользователя.
            expires_at: Момент окончания действия доступа. `None` —
                бессрочный доступ (`UNLIMITED_EXPIRE_AT`).
            sub_type: Уровень подписки — определяет squad'ы (см. `tier_map`).
            device_limit: Лимит устройств (HWID).

        Returns
            tuple: ({"remnawave": [id пользователя]}, ссылка на подписку).

        Raises
            RemnawaveInvalidExpiryError: Если `expires_at` не в будущем.
            RemnawaveError: Если `sub_type` не замаплен в `tier_map`.
            RemnawaveAuthError: Панель отклонила Bearer-токен.
            RemnawaveRequestError: Прочая ошибка панели.

        """
        expire_at = expires_at if expires_at is not None else self.UNLIMITED_EXPIRE_AT
        now = datetime.now(expire_at.tzinfo)
        if expire_at <= now:
            raise RemnawaveInvalidExpiryError(expires_at=expire_at)

        squads = self._squads_for_tier(sub_type)
        logger.info("Выдача доступа Remnawave tg_id={} до {}", tg_id, expire_at)

        existing = await self._get_user_by_tg_id(tg_id)
        if existing is not None:
            user = await self._patch_user(
                RemnawaveUserUpdate(
                    id=existing.id,
                    expire_at=expire_at,
                    hwid_device_limit=device_limit,
                    active_internal_squads=squads,
                )
            )
        else:
            user = await self._create_user(
                RemnawaveUserCreate(
                    username=f"u{tg_id}",
                    telegram_id=tg_id,
                    expire_at=expire_at,
                    hwid_device_limit=device_limit,
                    active_internal_squads=squads,
                )
            )

        logger.info("Доступ Remnawave выдан tg_id={} id={}", tg_id, user.id)
        return {"remnawave": [str(user.id)]}, user.subscription_url

    async def extend_config(
        self,
        config_ids: list[str],
        expires_at: datetime,
    ) -> list[str]:
        """Продлевает срок действия уже существующих конфигураций.

        Args:
            config_ids: Числовые id пользователей панели, которых нужно
                продлить (в виде строк).
            expires_at: Новый момент окончания действия.

        Returns
            list[str]: `config_id`, которые реально были найдены и продлены.

        Raises
            RemnawaveInvalidExpiryError: Если `expires_at` не в будущем.

        """
        now = datetime.now(expires_at.tzinfo)
        if expires_at <= now:
            raise RemnawaveInvalidExpiryError(expires_at=expires_at)

        return await self._set_users_expiry(config_ids, expires_at)

    async def set_unlimited_config(self, config_ids: list[str]) -> list[str]:
        """Снимает срок действия у уже существующих конфигураций.

        Args:
            config_ids: Числовые id пользователей панели (в виде строк).

        Returns
            list[str]: `config_id`, которые реально были найдены и обновлены.

        """
        return await self._set_users_expiry(config_ids, self.UNLIMITED_EXPIRE_AT)

    async def _set_users_expiry(
        self, config_ids: list[str], expire_at: datetime
    ) -> list[str]:
        """Находит пользователей по `id` и проставляет им `expireAt`.

        Общая часть `extend_config` и `set_unlimited_config`, различающихся
        только значением `expireAt`.
        """
        updated: list[str] = []
        for config_id in config_ids:
            user = await self._get_user_by_id(int(config_id))
            if user is None:
                continue
            await self._patch_user(RemnawaveUserUpdate(id=user.id, expire_at=expire_at))
            updated.append(config_id)

        logger.info(
            "Обновлён expireAt для {} из {} конфигураций Remnawave ({})",
            len(updated),
            len(config_ids),
            updated,
        )
        return updated

    async def set_tier(self, config_id: str, sub_type: str) -> None:
        """Переключает пользователя на squad'ы другого уровня подписки.

        Args:
            config_id: Числовой id пользователя на панели (в виде строки).
            sub_type: Новый уровень подписки (см. `tier_map`).

        Raises
            RemnawaveError: Если `sub_type` не замаплен в `tier_map`.
            RemnawaveUserNotFoundError: Если пользователь не найден на панели.

        """
        squads = self._squads_for_tier(sub_type)
        await self._patch_user(
            RemnawaveUserUpdate(id=int(config_id), active_internal_squads=squads)
        )

    async def delete_config(self, config_id: str) -> bool:
        """Удаляет пользователя с панели.

        Args:
            config_id: Числовой id пользователя на панели (в виде строки).

        Returns
            bool: `True`, если пользователь был найден и удалён. `False`,
                если пользователь уже отсутствует на панели.

        """
        try:
            await self._request("DELETE", f"{self.prefix}/users/{config_id}")
        except RemnawaveUserNotFoundError:
            return False
        return True

    def __repr__(self) -> str:
        """Строковое представление экземпляра класса (без токена)."""
        return f"RemnawaveAdapter(prefix={self.prefix}, squads={list(self.squads)})"
