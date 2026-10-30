"""Вспомогательные функции навигации для шаблонов админки."""

from urllib.parse import urlparse

from starlette.requests import Request


def resolve_back_url(request: Request, fallback: str) -> str:
    """Определяет адрес для кнопки «Назад» на карточке/странице админки.

    SQLAdmin хранит состояние списка (фильтры, поиск, страница) только в
    query-параметрах URL, а не в сессии, поэтому вернуться в ТОТ ЖЕ
    отфильтрованный список, с которого был переход по relation-ссылке,
    можно только по заголовку ``Referer`` — браузер подставляет его сам при
    обычной навигации по ссылке в рамках одного источника. Если заголовка
    нет или он ведёт на другой хост (нестандартный клиент, приватность
    браузера), используется запасной адрес.

    Args:
        request: Текущий запрос SQLAdmin.
        fallback: Адрес, на который вести, если `Referer` недоступен или
            ведёт на другой источник.

    Returns
        Адрес для перехода «назад».

    """
    referer = request.headers.get("referer")
    if referer and urlparse(referer).netloc == urlparse(str(request.url)).netloc:
        return referer
    return fallback
