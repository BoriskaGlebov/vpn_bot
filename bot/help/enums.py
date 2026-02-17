from enum import Enum


class DeviceEnum(str, Enum):
    """Список возможных устройств."""

    ANDROID = "android"
    IOS = "ios"
    PC = "pc"
    TV = "tv"
    SPLIT = "split"
