import json
import time
import uuid
from typing import Any

from app_error.base_error import AppError
from loguru import logger

from bot.app_error.api_error import APIClientConnectionError, APIClientError
from bot.core.config import settings_bot
from bot.integrations.api_client import APIClient
from bot.vpn.DTO import Inbound
from bot.vpn.schemas import S3XuiCredentials, S3XuiUSerSettings


class ThreeXUIAdapter:
    """Адаптер для взаимодействия с панелью 3x-ui.

    Инкапсулирует API-операции:
    - авторизация/разлогинивание
    - получение inbound-конфигураций
    - добавление пользователей
    - перезапуск XRay сервиса
    """

    def __init__(self, api_client: APIClient, prefix: str) -> None:
        """Инициализация адаптера.

        Args:
            api_client (APIClient): HTTP-клиент для работы с API панели.
            prefix (str): префикс API (например "/panel").

        """
        self.api = api_client
        self.prefix = prefix

    async def _login(
        self, user_credentials: S3XuiCredentials
    ) -> tuple[dict[str, Any], int]:
        """Авторизация в панели 3x-ui.

        Устанавливает сессию в API клиенте.

        Args:
            user_credentials: DTO с логином и паролем администратора.

        Returns
            tuple:
                - dict: ответ API
                - int: HTTP статус код

        Raises
            APIClientConnectionError: при ошибке соединения с API.

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
        """Выход из панели 3x-ui.

        Игнорирует ошибки API, так как операция не критична.
        """
        try:
            logger.info("Попытка выхода из 3x-ui")
            await self.api.get(
                url=f"{self.prefix}/logout",
            )
            logger.info("Успешный выход из 3x-ui")
        except APIClientError:
            logger.warning("Разлогинил пользователя.")

    async def _get_inbounds(self) -> list[Inbound]:
        """Получает список inbound-конфигураций из 3x-ui панели.

        Returns
            list[Inbound]: список inbound объектов.

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

    async def _add_user(
        self,
        inbound_id: int,
        user_add: S3XuiUSerSettings,
    ) -> tuple[dict[str, Any], int]:
        """Добавляет пользователя в указанный inbound.

        Args:
            inbound_id: ID inbound-конфигурации.
            user_add: настройки нового пользователя.

        Returns
            tuple:
                - dict[str, Any]: ответ API
                - int: HTTP статус код

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
        """Перезапускает XRay сервис.

        Returns
            Optional[tuple[dict, int]]:
                Ответ API или None при ошибке соединения.

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

    async def add_new_config(
        self,
        tg_id: int,
        days: int,
        port: int = 443,
        inb_name: str = "🇧🇬 test.x-ray-boriska.pro",
    ) -> type[str, str, str]:
        """Создание новой VPN-конфигурации для пользователя.

        Выполняет полный цикл:
        1. Авторизация в панели
        2. Поиск inbound
        3. Создание пользователя
        4. Добавление в inbound
        5. Перезапуск XRay
        6. Формирование subscription URL

        Args:
            tg_id (int): Telegram ID пользователя.
            days (int): срок действия конфигурации в днях.
            port (int, optional): порт inbound. Defaults to 443.
            inb_name (str, optional): имя inbound. Defaults to "🇧🇬 test.x-ray-boriska.pro".

        Returns
            tuple: (user_id, sub_id, subscription_url)

        Raises
            AppError: если inbound не найден.

        """
        logger.info("Создание новой конфигурации для tg_id={} на {} дней", tg_id, days)
        credentials = S3XuiCredentials(
            username=settings_bot.x_ray_username.get_secret_value(),
            password=settings_bot.x_ray_password.get_secret_value(),
        )
        await self._login(user_credentials=credentials)
        list_inbounds = await self._get_inbounds()
        inbound: Inbound | None = next(
            (i for i in list_inbounds if i.port == port and i.remark == inb_name), None
        )

        if inbound is None:
            logger.error("Inbound не найден: name={} port={}", inb_name, port)
            raise AppError(message=f"Не найден inbound {inb_name} на порту {port}")
        uid = str(uuid.uuid4())
        logger.debug("Сгенерирован UUID пользователя: {}", uid)
        user_add = S3XuiUSerSettings(
            id=uid,
            email=f"user_{tg_id}_{uid[:4]}",
            tgId=tg_id,
            subId=f"user_{tg_id}",
            flow="xtls-rprx-vision",
            limitIp=0,
            totalGB=0,
            expiryTime=(int(time.time()) * 1000) + days * 24 * 60 * 60 * 1000,
            reset=0,
            enable=True,
            comment="Пользователь добавил конфиг через бота",
        )

        await self._add_user(inbound_id=inbound.id, user_add=user_add)

        await self._restart_x_ray()
        await self._logout()
        url = (
            f"https://{settings_bot.x_ray_host}:{settings_bot.x_ray_subscription_port}/"
            f"{settings_bot.x_ray_subscription_prefix}/user_{tg_id}"
        )
        logger.info("Конфигурация успешно создана для tg_id={}", tg_id)
        return user_add.id, user_add.subId, url


# if __name__ == '__main__':
#     async def main():
#         user_cred = S3XuiCredentials(username=settings_bot.x_ray_username.get_secret_value(),
#                                      password=settings_bot.x_ray_password.get_secret_value())
#         client = APIClient(
#             base_url=settings_bot.x_ray_base_url_panel,
#             port=settings_bot.x_ray_panel_port,
#
#         )
#         adapter = ThreeXUIAdapter(api_client=client, prefix=f"/{settings_bot.x_ray_panel_prefix}")
#         res = await adapter.add_new_config(tg_id=456789,
#                                            days=33,
#                                            port=settings_bot.inbound_port,
#                                            inb_name=settings_bot.inbound_name, )
#         print(res)
#
#
#     asyncio.run(main())
