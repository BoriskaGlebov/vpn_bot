from enum import Enum


class DeviceEnum(str, Enum):
    """Список возможных устройств."""

    ANDROID = "android"
    IOS = "ios"
    PC = "pc"
    TV = "tv"
    SPLIT = "split"
    HAPP = "happ"
    INCY = "incy"
    ROUTING_HAPP = "routing_happ"
    ROUTING_INCY = "routing_incy"
