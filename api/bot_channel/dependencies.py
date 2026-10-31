from api.bot_channel.client import BotChannelClient
from api.core.config import settings_api


def get_bot_channel_client() -> BotChannelClient:
    """Возвращает клиент внутреннего канала api → bot.

    Клиент не держит соединений между вызовами, поэтому создаётся на запрос.

    Returns
        BotChannelClient: Клиент с настройками из `settings_api.bot_channel`.

    """
    return BotChannelClient(settings_api.bot_channel)
