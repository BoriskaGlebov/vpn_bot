import json
import time
import uuid
from typing import Any

from loguru import logger

from bot.app_error.api_error import APIClientConnectionError, APIClientError
from bot.app_error.base_error import AppError
from bot.core.config import SInbound
from bot.integrations.api_client import APIClient
from bot.vpn.DTO import Inbound, UserUUID
from bot.vpn.schemas import S3XuiCredentials, S3XuiUSerSettings


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

        """
        logger.debug(
            "Логинюсь в панели 3xui username={}",
            user_credentials.username,
        )

        res, s_code = await self.api.post(
            url=f"{self.prefix}/login",
            json=user_credentials.model_dump(),
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
            logger.info("Logout response обработан как successful: %s", e)
        logger.info("Сессия завершена (logout)")

    async def _get_all_inbounds(self) -> list[Inbound]:
        """Получает все inbound-конфигурации из панели.

        Returns
            list[Inbound]: Список inbound-объектов.

        Raises
            APIClientError: При ошибке API.

        """
        logger.info("Запрос списка inbound-конфигураций")
        data = await self.api.get(f"{self.prefix}/panel/api/inbounds/list")

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

        """
        logger.info("Запрос списка inbound-конфигураций")
        data = await self.api.get(f"{self.prefix}/panel/api/inbounds/list")

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

        return await self.api.post(
            url=f"{self.prefix}/panel/api/inbounds/addClient",
            json=payload,
        )

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
            AppError: Если найдено меньше inbound, чем ожидалось.

        """
        all_inbounds = await self._get_all_inbounds()
        allow_inb = {(cfg.port, cfg.name) for cfg in inbounds_cfg}
        find_inb = [inb for inb in all_inbounds if (inb.port, inb.remark) in allow_inb]
        if len(find_inb) < len(inbounds_cfg):
            logger.error(f"Не все Inbound найдены.{find_inb}")
            raise AppError(message=f"Не все  inbound найдены {find_inb}")
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
            AppError: При отсутствии необходимых inbound.
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
        url = f"https://{self.host}:{self.sub_port}/{self.sub_prefix}/user_{tg_id}"
        logger.info("Конфигурация успешно создана для tg_id={}", tg_id)
        return {
            "config_ids": list(user_add_info["config_ids"]),
            "sub_ids": list(user_add_info["sub_ids"]),
        }, url

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
