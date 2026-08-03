from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.users.schemas import SVPNConfigOut


class ConfigDeleteAction(StrEnum):
    """Действия при самостоятельном удалении пользователем своего VPN-конфига.

    Attributes
        CONFIRM: Пользователь выбрал конфиг для удаления — запрос подтверждения.
        EXECUTE: Пользователь подтвердил — выполнить удаление.
        CANCEL: Пользователь передумал — вернуться к списку без изменений.

    """

    CONFIRM = "confirm"
    EXECUTE = "execute"
    CANCEL = "cancel"


class ConfigDeleteCB(CallbackData, prefix="cfg_del"):  # type: ignore[misc,call-arg]
    """CallbackData для самостоятельного удаления пользователем своего конфига.

    Attributes
        action (ConfigDeleteAction): Шаг процесса удаления.
        config_id (int): ID конфига (`SVPNConfigOut.id`). Только id, а не
            file_name/pub_key — они не влезли бы в лимит Telegram на
            callback_data (64 байта), и при подтверждении данные конфига
            заново читаются по id из списка конфигов пользователя.

    """

    action: ConfigDeleteAction
    config_id: int


def my_configs_kb(configs: list[SVPNConfigOut]) -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру со списком конфигов пользователя для удаления.

    Args:
        configs: Список VPN-конфигов пользователя.

    Returns
        InlineKeyboardMarkup: По одной кнопке "🗑 {file_name}" на конфиг.

    """
    builder = InlineKeyboardBuilder()
    for config in configs:
        builder.button(
            text=f"🗑 {config.file_name}",
            callback_data=ConfigDeleteCB(
                action=ConfigDeleteAction.CONFIRM, config_id=config.id
            ),
        )
    builder.adjust(1)
    return builder.as_markup()


def confirm_delete_config_kb(config_id: int) -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру подтверждения удаления конфига.

    Args:
        config_id: ID конфига, который пользователь собирается удалить.

    Returns
        InlineKeyboardMarkup: Клавиатура с кнопками "Да, удалить" и "Отмена".

    """
    builder = InlineKeyboardBuilder()
    builder.button(
        text="✅ Да, удалить",
        callback_data=ConfigDeleteCB(
            action=ConfigDeleteAction.EXECUTE, config_id=config_id
        ),
    )
    builder.button(
        text="❌ Отмена",
        callback_data=ConfigDeleteCB(
            action=ConfigDeleteAction.CANCEL, config_id=config_id
        ),
    )
    builder.adjust(1)
    return builder.as_markup()


def proxy_url_button(url_proxy: str) -> InlineKeyboardMarkup:
    """Создаёт inline-клавиатуру для ссылки на Proxy."""
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="📨 Активировать прокси", url=url_proxy),
        InlineKeyboardButton(text="📋 Скопировать (долго жать) ссылку", url=url_proxy),
    )
    builder.adjust(1)
    return builder.as_markup()


def xray_url_kb(url: str) -> InlineKeyboardMarkup:
    """Клавиатура со ссылкой на подписку x-ray."""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📨 Долгое нажатие скопирует ссылку",
                    url=url,
                )
            ]
        ]
    )
    return keyboard
