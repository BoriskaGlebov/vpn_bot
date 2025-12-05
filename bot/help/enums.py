from enum import Enum


class DeviceEnum(str, Enum):
    ANDROID = "android"
    IOS = "ios"
    PC = "pc"
    TV = "tv"
