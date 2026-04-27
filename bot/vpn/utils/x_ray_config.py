import json
import time
import uuid
from typing import Any

from loguru import logger

from bot.app_error.api_error import APIClientConnectionError, APIClientError
from bot.app_error.base_error import AppError
from bot.core.config import SInbound, settings_bot
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

    async def _get_all_inbounds(self) -> list[Inbound]:
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
            Optional[tuple[dict[str, Any], int]]:
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

    async def _get_inbound(self, inbounds_cfg: list[SInbound]) -> list[Inbound]:
        """Фильтрует inbound-конфигурации по списку разрешённых.

        Args:
            inbounds_cfg (list[SInbound]): ожидаемые inbound (порт + имя).

        Returns
            list[Inbound]: найденные inbound-конфигурации.

        Raises
            AppError: если найдены не все inbound.

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
        inbounds: list[SInbound],
        tg_id: int,
        days: int = 0,
    ) -> tuple[dict[str, list[str]], str]:
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
            days (int): срок действия конфигурации в днях или ноль строкой для бесконечности.
            inbounds (list[SInbound]): Список доступных инбаундов

        Returns
            tuple:
                - dict[str, list[str]]: словарь с идентификаторами:
                    - config_ids: список UUID конфигов
                    - sub_ids: список subscription ID
                - str: subscription URL

        Raises
            AppError: если inbound не найден.

        """
        logger.info("Создание новой конфигурации для tg_id={} на {} дней", tg_id, days)
        credentials = S3XuiCredentials(
            username=settings_bot.x_ray_username.get_secret_value(),
            password=settings_bot.x_ray_password.get_secret_value(),
        )
        await self._login(user_credentials=credentials)
        inbounds_correct = await self._get_inbound(inbounds_cfg=inbounds)
        user_add_info = {"config_ids": set(), "sub_ids": set()}
        for inb in inbounds_correct:
            uid = str(uuid.uuid4())
            logger.debug("Сгенерирован UUID пользователя: {}", uid)
            remaining_days = (
                (int(time.time()) * 1000) + days * 24 * 60 * 60 * 1000
                if days > 0
                else 0
            )
            user_add = S3XuiUSerSettings(
                id=uid,
                email=f"user_{tg_id}_{uid[:4]}",
                tgId=tg_id,
                subId=f"user_{tg_id}",
                flow="xtls-rprx-vision",
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
        url = (
            f"https://{settings_bot.x_ray_host}:{settings_bot.x_ray_subscription_port}/"
            f"{settings_bot.x_ray_subscription_prefix}/user_{tg_id}"
        )
        logger.info("Конфигурация успешно создана для tg_id={}", tg_id)
        return {
            "config_ids": list(user_add_info["config_ids"]),
            "sub_ids": list(user_add_info["sub_ids"]),
        }, url

    async def delete_config(self, config_id: str, inbounds: list[SInbound]) -> bool:
        """Удаляет конфигурацию пользователя из указанных inbound.

        Args:
            config_id (str): UUID конфигурации пользователя.
            inbounds (list[SInbound]): список inbound, из которых нужно удалить.

        Returns
            bool: True при успешном выполнении.

        """
        cred = S3XuiCredentials(
            username=settings_bot.x_ray_username.get_secret_value(),
            password=settings_bot.x_ray_password.get_secret_value(),
        )
        await self._login(user_credentials=cred)
        correct_inbounds = await self._get_inbound(inbounds_cfg=inbounds)
        for inb in correct_inbounds:
            await self.api.post(
                url=f"{self.prefix}/panel/api/inbounds/{inb.id}/delClient/{config_id}",
            )
        await self._logout()
        return True


#
# if __name__ == '__main__':
#     async def main():
#         user_cred = S3XuiCredentials(username=settings_bot.x_ray_username.get_secret_value(),
#                                      password=settings_bot.x_ray_password.get_secret_value())
#         client = APIClient(
#             base_url=settings_bot.x_ray_base_url_panel,
#             port=settings_bot.x_ray_panel_port,
#             scheme="https"
#
#         )
#         adapter = ThreeXUIAdapter(api_client=client, prefix=f"/{settings_bot.x_ray_panel_prefix}")
#         # await adapter._login(user_credentials=user_cred)
#         # res = await adapter._get_all_inbounds()
#         # print(res)
#         # res2=await adapter._get_inbound(inbounds_cfg=settings_bot.inbounds)
#         # print(res2)
#         res, url = await adapter.add_new_config(tg_id=456789,
#                                                 days=33,
#                                                 inbounds=settings_bot.inbounds)
#         # print(res)
#         # print(res['config_ids'])
#         # print(res['sub_ids'])
#         # print(type(json.dumps(res['config_ids'])))
#         await asyncio.sleep(10)
#         for i in res['config_ids']:
#             res= await adapter.delete_config(config_id=i, inbounds=settings_bot.inbounds)
#             # print(res)
#             # await asyncio.sleep(3)
#
#
#     #
#     #
#     asyncio.run(main())
