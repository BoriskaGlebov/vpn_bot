import json
import time
import uuid
from typing import Any

from loguru import logger

from bot.app_error.api_error import APIClientConnectionError, APIClientError
from bot.core.config import SInbound
from bot.integrations.api_client import APIClient
from bot.vpn.DTO import Inbound, UserUUID
from bot.vpn.schemas import S3XuiCredentials, S3XuiUSerSettings
from bot.vpn.utils.x_ray_exceptions import (
    ThreeXUIAuthError,
    ThreeXUIConfigNotFoundError,
    ThreeXUIInboundNotFoundError,
    ThreeXUIInvalidExpiryError,
    ThreeXUIRequestError,
)


class ThreeXUIAdapter:
    """Адаптер для взаимодействия с панелью 3x-ui.

    Инкапсулирует HTTP-взаимодействие с API панели и предоставляет
    высокоуровневые операции управления пользователями и конфигурациями XRay.

    Основные возможности:
        - Авторизация и завершение сессии
        - Получение inbound-конфигураций
        - Добавление и удаление пользователей
        - Перезапуск XRay сервиса
        - Генерация subscription-ссылок

    Attributes
        api: HTTP-клиент для работы с API панели.
        prefix: Базовый префикс API (например, "/panel").
        inbounds_name: Список ожидаемых inbound-конфигураций.
        username: Логин администратора панели.
        password: Пароль администратора панели.
        host: Домен XRay-сервера.
        sub_port: Порт subscription endpoint.
        sub_prefix: Префикс subscription endpoint.
        location_prefix: Идентификатор местоположения сервера для БД.

    """

    def __init__(
        self,
        api_client: APIClient,
        prefix: str,
        correct_inbounds: list[SInbound],
        username: str,
        password: str,
        host: str,
        sub_port: int,
        sub_prefix: str,
        location_prefix: str,
    ) -> None:
        """Инициализирует адаптер 3x-ui.

        Args:
            api_client: HTTP-клиент для взаимодействия с API.
            prefix: Префикс API (например, "/panel").
            correct_inbounds: Список ожидаемых inbound-конфигураций.
            username: Логин администратора панели.
            password: Пароль администратора панели.
            host: Хост XRay-сервера.
            sub_port: Порт subscription endpoint.
            sub_prefix: Префикс subscription endpoint.
            location_prefix: Префикс локации для формирования subscription ID.

        """
        self.api = api_client
        self.prefix = prefix
        self.inbounds_name = correct_inbounds
        self.username = username
        self.password = password
        self.host = host
        self.sub_port = sub_port
        self.sub_prefix = sub_prefix
        self.location_prefix = location_prefix

    @staticmethod
    def _ensure_success(data: dict[str, Any], action: str) -> None:
        """Проверяет поле `success` в ответе панели 3x-ui.

        Панель 3x-ui в большинстве случаев отвечает HTTP 200 даже для
        логических ошибок (неверные креды, несуществующий клиент и т.д.),
        сигнализируя об этом полем `success: false` в теле ответа — такие
        ошибки не попадают в `APIClient._request` (там проверяется только
        HTTP статус-код), поэтому проверять их нужно здесь.

        Args:
            data: Тело ответа панели.
            action: Название операции — для сообщения об ошибке.

        Raises
            ThreeXUIRequestError: Если `data["success"]` не `True`.

        """
        if not data.get("success", False):
            raise ThreeXUIRequestError(action=action, reason=data.get("msg", ""))

    async def _login(
        self, user_credentials: S3XuiCredentials
    ) -> tuple[dict[str, Any], int]:
        """Авторизация в панели 3x-ui.

        Устанавливает сессию в API-клиенте.

        Args:
            user_credentials: Объект с логином и паролем администратора.

        Returns
            tuple: (response, status_code)
                response: Ответ API.
                status_code: HTTP статус-код.

        Raises
            APIClientConnectionError: При ошибке соединения с API.
            ThreeXUIAuthError: Если панель отклонила учётные данные.

        """
        logger.debug(
            "Логинюсь в панели 3xui username={}",
            user_credentials.username,
        )

        res, s_code = await self.api.post(
            url=f"{self.prefix}/login",
            json=user_credentials.model_dump(),
        )
        if not res.get("success", False):
            logger.error(
                "Ошибка авторизации в 3x-ui username={}: {}",
                user_credentials.username,
                res.get("msg"),
            )
            raise ThreeXUIAuthError(
                username=user_credentials.username, reason=res.get("msg", "")
            )
        logger.info("Успешная авторизация в 3x-ui (status={})", s_code)
        return res, s_code

    async def _logout(self) -> None:
        """Завершает сессию в панели 3x-ui.

        Ошибки игнорируются, так как операция не критична
        для дальнейшего выполнения.

        Raises
            APIClientError: Ошибка API игнорируется внутри метода.

        """
        try:
            logger.info("Попытка выхода из 3x-ui")
            await self.api.get(
                url=f"{self.prefix}/logout",
            )
            logger.info("Успешный выход из 3x-ui")
        except APIClientError as e:
            logger.info("Logout response обработан как successful: {}", e)
        logger.info("Сессия завершена (logout)")

    async def _get_all_inbounds(self) -> list[Inbound]:
        """Получает все inbound-конфигурации из панели.

        Returns
            list[Inbound]: Список inbound-объектов.

        Raises
            APIClientError: При ошибке API.
            ThreeXUIRequestError: Если панель ответила `success: false`.

        """
        logger.info("Запрос списка inbound-конфигураций")
        data = await self.api.get(f"{self.prefix}/panel/api/inbounds/list")
        self._ensure_success(data, action="get_inbounds_list")

        objs = data.get("obj", [])

        inbounds = [
            Inbound(
                id=item["id"],
                remark=item.get("remark"),
                enable=item.get("enable"),
                port=item.get("port"),
            )
            for item in objs
        ]

        logger.info("Получено inbound-конфигураций: {}", len(inbounds))
        return inbounds

    async def _get_all_users(self) -> list[UserUUID]:
        """Получает список всех пользователей (UUID) из inbound-конфигураций.

        Returns
            list[UserUUID]: Список UUID пользователей.

        Raises
            APIClientError: При ошибке запроса к API.
            ThreeXUIRequestError: Если панель ответила `success: false`.

        """
        logger.info("Запрос списка inbound-конфигураций")
        data = await self.api.get(f"{self.prefix}/panel/api/inbounds/list")
        self._ensure_success(data, action="get_inbounds_list")

        objs = data.get("obj", [])
        user_uuids: list[UserUUID] = []
        for obj in objs:
            for user in obj["clientStats"]:
                user_uuids.append(UserUUID(conf_uuid=user["uuid"]))
        logger.info("Получено идентификаторы-пользователей: {}", len(user_uuids))
        return user_uuids

    async def _add_user(
        self,
        inbound_id: int,
        user_add: S3XuiUSerSettings,
    ) -> tuple[dict[str, Any], int]:
        """Добавляет пользователя в указанную inbound-конфигурацию.

        Args:
            inbound_id: Идентификатор inbound.
            user_add: Параметры создаваемого пользователя.

        Returns
            tuple: (response, status_code)
                response: Ответ API.
                status_code: HTTP статус-код.

        Raises
            APIClientError: При ошибке API.
            ThreeXUIRequestError: Если панель ответила `success: false`.

        """
        client_dict = user_add.model_dump()

        settings = json.dumps({"clients": [client_dict]}, separators=(",", ":"))

        payload = {
            "id": inbound_id,
            "settings": settings,
        }

        logger.info(
            "Добавление пользователя в inbound_id={} tg_id={}",
            inbound_id,
            user_add.tgId,
        )
        logger.debug("Payload add user: {}", payload)

        data, s_code = await self.api.post(
            url=f"{self.prefix}/panel/api/inbounds/addClient",
            json=payload,
        )
        self._ensure_success(data, action="add_client")
        return data, s_code

    async def _get_inbound_clients(self, inbound_id: int) -> list[dict[str, Any]]:
        """Возвращает клиентов (`settings.clients`) inbound-конфигурации.

        Нужен для продления существующих конфигураций: `updateClient`
        полностью заменяет объект клиента на панели, поэтому перед
        изменением `expiryTime` нужно сначала получить его текущие поля
        (email, subId, flow и т.д.), чтобы их не потерять.

        Args:
            inbound_id: Идентификатор inbound.

        Returns
            list[dict[str, Any]]: Список клиентов в «сыром» виде (как в панели).

        Raises
            APIClientError: При ошибке API.
            ThreeXUIRequestError: Если панель ответила `success: false`.

        """
        data = await self.api.get(f"{self.prefix}/panel/api/inbounds/get/{inbound_id}")
        self._ensure_success(data, action="get_inbound")

        obj = data.get("obj") or {}
        clients: list[dict[str, Any]] = json.loads(obj.get("settings") or "{}").get(
            "clients", []
        )
        return clients

    async def _update_client(
        self,
        inbound_id: int,
        client_id: str,
        client: dict[str, Any],
    ) -> tuple[dict[str, Any], int]:
        """Обновляет существующего клиента в указанной inbound-конфигурации.

        Args:
            inbound_id: Идентификатор inbound, которому принадлежит клиент.
            client_id: UUID клиента (совпадает с `client["id"]`).
            client: Полный объект клиента (см. `_get_inbound_clients`) с уже
                применёнными изменениями — панель заменяет клиента целиком.

        Returns
            tuple: (response, status_code)
                response: Ответ API.
                status_code: HTTP статус-код.

        Raises
            APIClientError: При ошибке API.
            ThreeXUIRequestError: Если панель ответила `success: false`.

        """
        settings = json.dumps({"clients": [client]}, separators=(",", ":"))
        payload = {
            "id": inbound_id,
            "settings": settings,
        }

        logger.info(
            "Обновление клиента client_id={} inbound_id={}", client_id, inbound_id
        )
        logger.debug("Payload update client: {}", payload)

        data, s_code = await self.api.post(
            url=f"{self.prefix}/panel/api/inbounds/updateClient/{client_id}",
            json=payload,
        )
        self._ensure_success(data, action="update_client")
        return data, s_code

    async def _restart_x_ray(self) -> tuple[dict[str, Any], int] | None:
        """Перезапускает сервис XRay.

        Returns
            Optional[tuple]: Ответ API при успехе, иначе None.

        Notes
            Может возвращать None при активных соединениях или
            недоступности сервера.

        """
        try:
            logger.warning("Перезапуск XRay сервиса")
            result = await self.api.post(
                f"{self.prefix}/panel/api/server/restartXrayService"
            )
            logger.info("XRay успешно перезапущен")
            return result
        except APIClientConnectionError:
            logger.warning("Ошибка перезапуска XRay (возможно активные соединения VPN)")
            return None

    async def _get_inbound(self, inbounds_cfg: list[SInbound]) -> list[Inbound]:
        """Получает inbound-конфигурации, соответствующие заданным критериям.

        Сопоставление выполняется по портам и имени (remark).

        Args:
            inbounds_cfg: Список ожидаемых inbound-конфигураций.

        Returns
            list[Inbound]: Найденные inbound-конфигурации.

        Raises
            ThreeXUIInboundNotFoundError: Если найдено меньше inbound, чем ожидалось.

        """
        all_inbounds = await self._get_all_inbounds()
        allow_inb = {(cfg.port, cfg.name) for cfg in inbounds_cfg}
        find_inb = [inb for inb in all_inbounds if (inb.port, inb.remark) in allow_inb]
        if len(find_inb) < len(inbounds_cfg):
            logger.error(f"Не все Inbound найдены.{find_inb}")
            raise ThreeXUIInboundNotFoundError(
                expected=len(inbounds_cfg), found=find_inb
            )
        return find_inb

    async def add_new_config(
        self,
        tg_id: int,
        days: int = 0,
    ) -> tuple[dict[str, list[str]], str]:
        """Создаёт новую VPN-конфигурацию пользователя.

        Полный цикл:
            1. Авторизация
            2. Получение inbound-конфигураций
            3. Генерация пользователя
            4. Добавление пользователя в inbound
            5. Перезапуск XRay
            6. Формирование subscription URL

        Args:
            tg_id: Telegram ID пользователя.
            days: Срок действия конфигурации в днях.
                0 — бессрочная конфигурация.

        Returns
            tuple: (
                dict: {
                    "config_ids": list[str],
                    "sub_ids": list[str]
                },
                subscription_url: str
            )

        Raises
            ThreeXUIInboundNotFoundError: При отсутствии необходимых inbound.
            ThreeXUIRequestError: Если панель ответила `success: false`.
            APIClientError: При ошибках API.

        """
        logger.info("Создание новой конфигурации для tg_id={} на {} дней", tg_id, days)
        credentials = S3XuiCredentials(
            username=self.username,
            password=self.password,
        )
        await self._login(user_credentials=credentials)
        inbounds_correct = await self._get_inbound(inbounds_cfg=self.inbounds_name)
        user_add_info = {"config_ids": set(), "sub_ids": set()}
        for inb in inbounds_correct:
            uid = str(uuid.uuid4())
            logger.debug("Сгенерирован UUID пользователя: {}", uid)
            remaining_days = (
                (int(time.time()) * 1000) + days * 24 * 60 * 60 * 1000
                if days > 0
                else 0
            )
            # У подключения XHTTP нет параметра flow предается пустая строка.
            flow = "xtls-rprx-vision" if "XHTTP" not in inb.remark else ""
            user_add = S3XuiUSerSettings(
                id=uid,
                email=f"user_{tg_id}_{uid[:4]}",
                tgId=tg_id,
                subId=f"{self.location_prefix}user_{tg_id}",
                flow=flow,
                limitIp=0,
                totalGB=0,
                expiryTime=remaining_days,
                reset=0,
                enable=True,
                comment="Пользователь добавил конфиг через бота",
            )
            user_add_info["config_ids"].add(user_add.id)
            user_add_info["sub_ids"].add(user_add.subId)
            await self._add_user(inbound_id=inb.id, user_add=user_add)

        await self._restart_x_ray()
        await self._logout()
        url = f"https://{self.host}:{self.sub_port}/{self.sub_prefix}/{self.location_prefix}user_{tg_id}"
        logger.info("Конфигурация успешно создана для tg_id={}", tg_id)
        return {
            "config_ids": list(user_add_info["config_ids"]),
            "sub_ids": list(user_add_info["sub_ids"]),
        }, url

    async def extend_config(
        self,
        config_ids: list[str],
        days: int,
    ) -> list[str]:
        """Продлевает срок действия уже существующих VPN-конфигураций пользователя.

        В отличие от `add_new_config`, не создаёт новых клиентов, а находит
        уже существующие по их `config_id` среди ожидаемых inbound этой ноды
        и обновляет только `expiryTime`/`enable`, не трогая остальные поля
        клиента (email, subId, flow и т.д.).

        Полный цикл:
            1. Авторизация.
            2. Получение ожидаемых inbound-конфигураций.
            3. Поиск клиентов с указанными `config_id` среди клиентов каждого
               inbound.
            4. Обновление найденных клиентов новым `expiryTime`.
            5. Перезапуск XRay.

        Так как каждый `config_id` из `add_new_config` создаётся один раз на
        конкретный inbound, часть `config_ids` может не найтись на этой ноде —
        это нормально, если у пользователя есть конфиги ещё и на других
        XRay-нодах (см. `XRayRegistry.all()`), поэтому такие id просто
        пропускаются, а не считаются ошибкой сами по себе.

        Args:
            config_ids: UUID существующих конфигураций клиента, которые нужно
                продлить.
            days: Новый срок действия в днях от текущего момента. Должен быть
                больше 0 — бессрочные конфиги (`expiryTime=0`) через этот
                метод не создаются и не проставляются.

        Returns
            list[str]: `config_id` конфигураций, которые реально были найдены
                и продлены. Может быть короче `config_ids`, если часть из них
                принадлежит другой XRay-ноде — вызывающий код должен повторить
                вызов для оставшихся `config_id` на других нодах реестра.

        Raises
            ThreeXUIInvalidExpiryError: Если `days <= 0`.
            ThreeXUIInboundNotFoundError: Если не все ожидаемые inbound найдены.
            ThreeXUIConfigNotFoundError: Если ни один `config_id` не найден ни
                в одном inbound этой ноды.
            ThreeXUIRequestError: Если панель ответила `success: false`.
            APIClientError: При ошибках API.

        """
        if days <= 0:
            raise ThreeXUIInvalidExpiryError(days=days)

        logger.info("Продление конфигураций {} на {} дней", config_ids, days)

        credentials = S3XuiCredentials(
            username=self.username,
            password=self.password,
        )
        await self._login(user_credentials=credentials)
        inbounds_correct = await self._get_inbound(inbounds_cfg=self.inbounds_name)
        new_expiry = (int(time.time()) * 1000) + days * 24 * 60 * 60 * 1000

        pending = set(config_ids)
        extended: list[str] = []

        for inb in inbounds_correct:
            if not pending:
                break
            clients = await self._get_inbound_clients(inb.id)
            for client in clients:
                client_id = client.get("id")
                if client_id not in pending:
                    continue
                client["expiryTime"] = new_expiry
                client["enable"] = True
                await self._update_client(
                    inbound_id=inb.id, client_id=client_id, client=client
                )
                extended.append(client_id)
                pending.discard(client_id)

        await self._restart_x_ray()
        await self._logout()

        if not extended:
            raise ThreeXUIConfigNotFoundError(config_ids=config_ids)

        logger.info(
            "Продлено конфигураций: {} из {} ({})",
            len(extended),
            len(config_ids),
            extended,
        )
        return extended

    async def delete_config(
        self,
        config_id: str,
    ) -> bool:
        """Удаляет конфигурацию пользователя из всех inbound.

        Args:
            config_id: UUID конфигурации пользователя.

        Returns
            bool: True, если удаление выполнено успешно,
            False если конфигурация не найдена.

        Raises
            APIClientError: При ошибке API.

        """
        cred = S3XuiCredentials(
            username=self.username,
            password=self.password,
        )
        await self._login(user_credentials=cred)
        user_id = await self._get_all_users()
        if UserUUID(conf_uuid=config_id) not in user_id:
            logger.debug(f"{config_id} -  нет такого на этом сервер.")
            return False
        correct_inbounds = await self._get_inbound(inbounds_cfg=self.inbounds_name)
        for inb in correct_inbounds:
            await self.api.post(
                url=f"{self.prefix}/panel/api/inbounds/{inb.id}/delClient/{config_id}",
            )
        await self._logout()
        return True

    def __repr__(self) -> str:
        """Строковое представление экземпляра класса.

        Returns
            str: Краткое описание адаптера (host, prefix, inbound count, username).

        """
        return (
            f"ThreeXUIAdapter("
            f"host={self.host}, "
            f"prefix={self.prefix}, "
            f"inbounds={len(self.inbounds_name)}, "
            f"username={self.username}"
            f")"
        )


class XRayRegistry:
    """Реестр XRay-адаптеров.

    Хранит набор адаптеров ThreeXUIAdapter, сопоставленных с именами VPN-нод,
    и предоставляет методы для их получения.

    Используется сервисами для выбора конкретной XRay-ноды при выполнении
    операций (создание пользователя, выдача подписки и т.д.).

    Attributes
        _adapters (dict[str, ThreeXUIAdapter]):
            Словарь адаптеров, где ключ — имя ноды, значение — адаптер XRay.

    Args
        adapters (dict[str, ThreeXUIAdapter]):
            Предварительно созданные адаптеры XRay, сгруппированные по именам нод.

    Notes
        - Класс не изменяет переданный словарь и не управляет жизненным циклом адаптеров.
        - Не выполняет выбор ноды — только предоставляет доступ.
        - Валидация наличия ключа делегируется вызывающему коду.

    """

    def __init__(self, adapters: dict[str, ThreeXUIAdapter]) -> None:
        self._adapters = adapters

    def get(self, name: str) -> ThreeXUIAdapter:
        """Возвращает адаптер по имени ноды.

        Args:
            name (str): Имя VPN-ноды.

        Returns
            ThreeXUIAdapter: Адаптер, соответствующий указанной ноде.

        Raises
            KeyError: Если адаптер с таким именем не найден.

        """
        return self._adapters[name]

    def all(self) -> list[ThreeXUIAdapter]:
        """Возвращает список всех доступных адаптеров.

        Returns
            list[ThreeXUIAdapter]: Список всех зарегистрированных XRay-адаптеров.

        """
        return list(self._adapters.values())

    def __repr__(self) -> str:
        """Строковое представление экземпляра класса."""
        return f"XRayRegistry(adapters={list(self._adapters.keys())})"
