from enum import StrEnum


class VPNBackend(StrEnum):
    """Бэкенд, которым обслуживается конфигурация.

    Определяет, какой адаптер (SSH-клиент Amnezia или ThreeXUIAdapter)
    нужно использовать для продления/удаления конфига.

    Attributes
        AMNEZIA: WireGuard/AmneziaWG, управление через SSH.
        XRAY: XRay/VLESS через панель 3x-ui.

    """

    AMNEZIA = "amnezia"
    XRAY = "xray"


class VPNProtocol(StrEnum):
    """Конкретный протокол/версия внутри бэкенда.

    Значения пишутся в колонку `VPNConfig.protocol` как обычные строки
    (не native enum в postgres — см. комментарий в `api/vpn/models.py`),
    поэтому в БД могут встречаться и значения вне этого перечисления
    (старые записи, новые протоколы). Enum нужен на стороне записи, чтобы
    название протокола не расползалось по коду строковыми литералами.

    Attributes
        WG_V1: AmneziaWG, первая версия протокола.
        WG_V2: AmneziaWG, вторая версия протокола.
        WG_V3: AmneziaWG, третья версия протокола.
        VLESS_REALITY_TCP: VLESS Reality поверх TCP (с flow xtls-rprx-vision).
        VLESS_REALITY_XHTTP: VLESS Reality поверх XHTTP (без flow).

    """

    WG_V1 = "wg_v1"
    WG_V2 = "wg_v2"
    WG_V3 = "wg_v3"
    VLESS_REALITY_TCP = "vless_reality_tcp"
    VLESS_REALITY_XHTTP = "vless_reality_xhttp"

    @classmethod
    def for_wg(cls, protocol_version: str) -> "VPNProtocol":
        """Возвращает протокол AmneziaWG по версии протокола ноды.

        Args:
            protocol_version (str): Версия протокола ноды ("v1" | "v2" | "v3"),
                см. `VPNNode.protocol_version` в `bot/core/config.py`.

        Returns
            VPNProtocol: Соответствующее значение `WG_V*`.

        Raises
            ValueError: Если версия протокола неизвестна.

        """
        return cls(f"wg_{protocol_version}")
