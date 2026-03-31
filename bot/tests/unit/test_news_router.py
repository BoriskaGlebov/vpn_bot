from unittest.mock import AsyncMock

import pytest
from aiogram.types import CallbackQuery, Message

from bot.news.router import NewsRouter, NewStates
from bot.news.services import NewsService


@pytest.mark.asyncio
@pytest.mark.news
async def test_start_handler_sets_state_and_sends_message(
    fake_bot, make_fake_message, fake_state, fake_logger, news_adapter_mock
) -> None:
    """Тест стартового хэндлера /news.

    Проверяет:
        1. Отправку приветственного сообщения пользователю.
        2. Установку состояния FSM в `NewStates.news_start`.
    """
    message: Message = make_fake_message(text="/news")
    news_service = NewsService(adapter=news_adapter_mock)
    router = NewsRouter(bot=fake_bot, logger=fake_logger, news_service=news_service)

    await router.start_handler(message=message, state=fake_state)

    message.answer.assert_awaited_once()
    fake_state.set_state.assert_awaited_once_with(NewStates.news_start)


@pytest.mark.asyncio
@pytest.mark.news
async def test_news_text_handler_text_saves_data_and_sets_state(
    fake_bot, make_fake_message, fake_state, fake_logger, news_adapter_mock
) -> None:
    """Тест хэндлера ввода текста новости.

    Проверяет:
        1. Сохранение текста новости в FSMContext.
        2. Переход состояния FSM в `NewStates.confirm_news`.
        3. Отправку подтверждающего сообщения пользователю.
    """
    message: Message = make_fake_message(text="Test news")
    news_service = NewsService(adapter=news_adapter_mock)
    router = NewsRouter(bot=fake_bot, logger=fake_logger, news_service=news_service)

    await router.news_text_handler(message=message, state=fake_state)

    fake_state.update_data.assert_awaited()
    fake_state.set_state.assert_awaited_with(NewStates.confirm_news)
    message.answer.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.news
async def test_news_text_handler_photo_saves_data_and_sets_state(
    fake_bot, make_fake_photo, fake_state, fake_logger, news_adapter_mock
) -> None:
    """Тест хэндлера фото новости.

    Проверяет:
        1. Сохранение фото в FSMContext.
        2. Переход состояния FSM в `NewStates.confirm_news`.
        3. Отправку подтверждающего фото пользователю.
    """
    message: Message = make_fake_photo()
    news_service = NewsService(adapter=news_adapter_mock)
    router = NewsRouter(bot=fake_bot, logger=fake_logger, news_service=news_service)

    await router.news_text_handler(message=message, state=fake_state)

    fake_state.update_data.assert_awaited()
    fake_state.set_state.assert_awaited_with(NewStates.confirm_news)
    message.answer_photo.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.news
async def test_confirm_news_handler_sends_messages_and_edits_preview(
    fake_bot, make_query_photo, fake_state, fake_logger, news_adapter_mock
) -> None:
    """Тест подтверждения рассылки новости.

    Проверяет:
        1. Получение списка пользователей через `NewsService.all_users_id`.
        2. Отправку сообщений каждому пользователю.
        3. Очистку FSMContext после рассылки.
        4. Ответ на CallbackQuery.
    """
    query: CallbackQuery = make_query_photo()
    msg: Message = query.message
    news_service = NewsService(adapter=news_adapter_mock)
    news_service.all_users_id = AsyncMock(return_value=[111, 222])
    fake_state.get_data.return_value = {
        "news": {"content_type": "text", "text": "Hello!"}
    }

    router = NewsRouter(bot=fake_bot, logger=fake_logger, news_service=news_service)

    await router.confirm_news_handler(query=query, state=fake_state)

    assert fake_bot.send_message.await_count == 2
    msg.edit_text.assert_not_called()
    fake_state.clear.assert_awaited()
    query.answer.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.news
async def test_cancel_news_handler_edits_message_and_clears_state(
    make_fake_query,
    fake_logger,
    fake_state,
    fake_bot,
    make_query_photo,
    news_adapter_mock,
) -> None:
    """Тест отмены рассылки новости пользователем.

    Проверяет:
        1. Редактирование текста или подписи сообщения на ❌ Рассылка отменена.
        2. Очистку FSMContext.
        3. Ответ на CallbackQuery.
    """
    news_service = NewsService(adapter=news_adapter_mock)
    router = NewsRouter(bot=fake_bot, logger=fake_logger, news_service=news_service)

    # === Тест для текстового сообщения ===
    query_text: CallbackQuery = make_fake_query()
    msg_text: Message = query_text.message

    await router.cancel_news_handler(query=query_text, state=fake_state)

    fake_bot.edit_message_text.assert_awaited_once_with(
        chat_id=999, message_id=1999, text="❌ Рассылка отменена."
    )
    fake_state.clear.assert_awaited()
    query_text.answer.assert_awaited()

    # Сбрасываем mock-объекты
    msg_text.edit_text.reset_mock()
    fake_state.clear.reset_mock()
    query_text.answer.reset_mock()

    # === Тест для сообщения с фото ===
    query_photo: CallbackQuery = make_query_photo()

    await router.cancel_news_handler(query=query_photo, state=fake_state)

    fake_bot.edit_message_caption.assert_awaited_once_with(
        chat_id=999,
        message_id=1999,
        caption="❌ Рассылка отменена.",
    )
    fake_state.clear.assert_awaited()
    query_photo.answer.assert_awaited()
