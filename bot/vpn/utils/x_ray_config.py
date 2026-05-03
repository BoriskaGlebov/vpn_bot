import json
import time
import uuid
from typing import Any

from loguru import logger

from bot.app_error.api_error import APIClientConnectionError, APIClientError
from bot.app_error.base_error import AppError
from bot.core.config import SInbound
from bot.integrations.api_client import APIClient
from bot.vpn.DTO import Inbound
from bot.vpn.schemas import S3XuiCredentials, S3XuiUSerSettings


# TODO тесты
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
        api (APIClient): HTTP-клиент для работы с API панели.
        prefix (str): Базовый префикс API (например, "/panel").
        inbounds_name (list[SInbound]): Список ожидаемых inbound-конфигураций.
        username (str): Логин администратора панели.
        password (str): Пароль администратора панели.
        host (str): Домен XRay-сервера.
        sub_port (int): Порт subscription endpoint.
        sub_prefix (str): Префикс subscription endpoint.

    """

    # TODO докумнетация
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
    ) -> None:
        """Инициализирует адаптер 3x-ui.

        Args:
            api_client (APIClient): HTTP-клиент.
            prefix (str): Префикс API (например, "/panel").
            correct_inbounds (list[SInbound]): Ожидаемые inbound-конфигурации.
            username (str): Логин администратора панели.
            password (str): Пароль администратора панели.
            host (str): Хост XRay.
            sub_port (int): Порт subscription endpoint.
            sub_prefix (str): Префикс subscription endpoint.

        """
        self.api = api_client
        self.prefix = prefix
        self.inbounds_name = correct_inbounds
        self.username = username
        self.password = password
        self.host = host
        self.sub_port = sub_port
        self.sub_prefix = sub_prefix

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
        """Завершает сессию в панели 3x-ui.

        Ошибки игнорируются, так как операция не критична
        и не влияет на дальнейшее выполнение.
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

    async def _add_user(
        self,
        inbound_id: int,
        user_add: S3XuiUSerSettings,
    ) -> tuple[dict[str, Any], int]:
        """Добавляет пользователя в inbound.

        Args:
            inbound_id (int): ID inbound-конфигурации.
            user_add (S3XuiUSerSettings): DTO с настройками пользователя.

        Returns
            tuple[dict[str, Any], int]:
                - Ответ API
                - HTTP статус код

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
        """Перезапускает XRay сервис.

        Returns
            tuple[dict[str, Any], int] | None:
                Ответ API или None при ошибке соединения.

        Notes
            Ошибка может возникнуть при активных соединениях или недоступности сервера.

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
        """Возвращает inbound-конфигурации, соответствующие ожидаемым.

        Сопоставление происходит по:
            - port
            - remark (name)

        Args:
            inbounds_cfg (list[SInbound]): Ожидаемые inbound-конфигурации.

        Returns
            list[Inbound]: Найденные inbound.

        Raises
            AppError: Если найдено меньше inbound, чем ожидается.

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
        """Создаёт новую VPN-конфигурацию для пользователя.

        Полный цикл:
            1. Авторизация
            2. Получение inbound
            3. Генерация пользователя
            4. Добавление в каждый inbound
            5. Перезапуск XRay
            6. Формирование subscription URL

        Args:
            tg_id (int): Telegram ID пользователя.
            days (int, optional): Срок действия в днях.
                0 — бессрочная конфигурация.

        Returns
            tuple[dict[str, list[str]], str]:
                - Словарь:
                    - config_ids: list[str] — UUID конфигов
                    - sub_ids: list[str] — subscription ID
                - subscription URL

        Raises
            AppError: Если inbound не найден.
            APIClientError: При ошибке API.

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
            flow = "xtls-rprx-vision" if "XHTTP" not in inb.remark else ""
            user_add = S3XuiUSerSettings(
                id=uid,
                email=f"user_{tg_id}_{uid[:4]}",
                tgId=tg_id,
                subId=f"user_{tg_id}",
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
        """Удаляет конфигурацию пользователя из всех целевых inbound.

        Args:
            config_id (str): UUID конфигурации.

        Returns
            bool: True при успешном выполнении.

        Raises
            APIClientError: При ошибке API.

        """
        cred = S3XuiCredentials(
            username=self.username,
            password=self.password,
        )
        await self._login(user_credentials=cred)
        correct_inbounds = await self._get_inbound(inbounds_cfg=self.inbounds_name)
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
