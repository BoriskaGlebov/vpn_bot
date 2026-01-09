from unittest.mock import AsyncMock

import pytest
from aiogram.types import CallbackQuery, Message

from bot.news.keyboards.inline_kb import NewsAction, NewsCB
from bot.news.router import NewsRouter, NewStates
from bot.news.services import NewsService


@pytest.mark.asyncio
@pytest.mark.news
async def test_start_handler_sets_state_and_sends_message(
    fake_bot, make_fake_message, fake_state, fake_logger
):
    message: Message = make_fake_message(text="/news")
    news_service = NewsService(bot=fake_bot, logger=fake_logger)
    router = NewsRouter(bot=fake_bot, logger=fake_logger, news_service=news_service)

    await router.start_handler(message=message, state=fake_state)

    message.answer.assert_awaited_once()
    fake_state.set_state.assert_awaited_once_with(NewStates.news_start)


@pytest.mark.asyncio
@pytest.mark.news
async def test_news_text_handler_text_saves_data_and_sets_state(
    fake_bot, make_fake_message, fake_state, fake_logger
):
    message: Message = make_fake_message(text="Test news")
    # message.text = "Test news"
    news_service = NewsService(bot=fake_bot, logger=fake_logger)
    router = NewsRouter(bot=fake_bot, logger=fake_logger, news_service=news_service)

    await router.news_text_handler(message, state=fake_state)

    fake_state.update_data.assert_awaited()
    fake_state.set_state.assert_awaited_with(NewStates.confirm_news)
    message.answer.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.news
async def test_news_text_handler_photo_saves_data_and_sets_state(
    fake_bot, make_fake_photo, fake_state, fake_logger
):
    message: Message = make_fake_photo()
    news_service = NewsService(bot=fake_bot, logger=fake_logger)
    router = NewsRouter(bot=fake_bot, logger=fake_logger, news_service=news_service)

    await router.news_text_handler(message=message, state=fake_state)

    fake_state.update_data.assert_awaited()
    fake_state.set_state.assert_awaited_with(NewStates.confirm_news)
    message.answer_photo.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.news
async def test_confirm_news_handler_sends_messages_and_edits_preview(
    fake_bot, make_query_photo, fake_state, session, fake_logger
):
    query: CallbackQuery = make_query_photo()
    msg: Message = query.message
    news_service = NewsService(bot=fake_bot, logger=fake_logger)

    # Подменяем метод all_users_id, чтобы вернуть тестовых пользователей
    news_service.all_users_id = AsyncMock(return_value=[111, 222])

    # Заполняем FSMContext данными новости
    fake_state.get_data.return_value = {
        "news": {"content_type": "text", "text": "Hello!"}
    }

    router = NewsRouter(bot=fake_bot, logger=fake_logger, news_service=news_service)

    await router.confirm_news_handler(query=query, session=session, state=fake_state)

    assert fake_bot.send_message.await_count == 2
    msg.edit_text.assert_not_called()  # для текста edit_message_text вызывается бот
    fake_state.clear.assert_awaited()
    query.answer.assert_awaited()


@pytest.mark.asyncio
@pytest.mark.news
async def test_cancel_news_handler_edits_message_and_clears_state(
    make_fake_query, fake_logger, fake_state, fake_bot
):
    query: CallbackQuery = make_fake_query()
    msg: Message = query.message
    news_service = NewsService(bot=fake_bot, logger=fake_logger)
    router = NewsRouter(bot=fake_bot, logger=fake_logger, news_service=news_service)

    await router.cancel_news_handler(query=query, state=fake_state)

    msg.edit_text.assert_awaited_once_with("❌ Рассылка отменена.")
    fake_state.clear.assert_awaited()
    query.answer.assert_awaited()
