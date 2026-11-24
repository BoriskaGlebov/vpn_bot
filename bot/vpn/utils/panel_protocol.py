from datetime import datetime
from typing import Protocol


class PanelAdapter(Protocol):
    """Общий интерфейс адаптера панели управления VPN-конфигурациями.

    Абстрагирует сервисный слой (`VPNService`, `SchedulerBotService`) от
    конкретной панели (3x-ui, в будущем — Remnawave), чтобы добавление
    нового бэкенда не требовало ветвления по типу адаптера.
    """

    async def extend_config(
        self, config_ids: list[str], expires_at: datetime
    ) -> list[str]:
        """Продлевает срок действия указанных конфигураций.

        Args:
            config_ids: Идентификаторы конфигураций для продления.
            expires_at: Новый момент окончания действия конфигураций.

        Returns
            list[str]: Идентификаторы успешно продлённых конфигураций.

        """
        ...

    async def set_unlimited_config(self, config_ids: list[str]) -> list[str]:
        """Снимает срок действия с указанных конфигураций (бессрочная подписка).

        Args:
            config_ids: Идентификаторы конфигураций.

        Returns
            list[str]: Идентификаторы конфигураций, с которых снят срок действия.

        """
        ...

    async def delete_config(self, config_id: str) -> bool:
        """Удаляет конфигурацию с панели.

        Args:
            config_id: Идентификатор конфигурации.

        Returns
            bool: `True`, если конфигурация была найдена и удалена.

        """
        ...
