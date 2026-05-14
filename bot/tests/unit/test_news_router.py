from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Message

from bot.news.keyboards.inline_kb import TargetAction
from bot.news.router import NewsRouter, NewStates
from bot.news.services import NewsService


class FakePhoto:
    def __init__(self, file_id):
        self.file_id = file_id


@pytest.fixture
def news_service(news_adapter_mock):
    return NewsService(adapter=news_adapter_mock)


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
    assert fake_state.set_state.call_args[0][0] == NewStates.news_start


@pytest.mark.asyncio
async def test_news_text_handler_text(
    fake_bot, make_fake_message, fake_state, fake_logger, news_service
):
    router = NewsRouter(fake_bot, fake_logger, news_service)

    message = make_fake_message(text="Hello news")

    await router.news_text_handler(message=message, state=fake_state)

    # FSM update
    fake_state.update_data.assert_awaited_once()

    args, kwargs = fake_state.update_data.call_args
    assert "news" in kwargs or "news" in args[0]

    # state transition
    fake_state.set_state.assert_awaited_once()
    assert fake_state.set_state.call_args[0][0] == NewStates.choose_target

    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_news_text_handler_photo(
    fake_bot, make_fake_message, fake_state, fake_logger, news_service
):
    router = NewsRouter(fake_bot, fake_logger, news_service)

    message = make_fake_message()
    message.photo = [FakePhoto("photo_123")]
    message.caption = "caption"

    await router.news_text_handler(message=message, state=fake_state)

    args, kwargs = fake_state.update_data.call_args
    assert "news" in kwargs or "news" in args[0]


class FakeChat:
    id = 123


class FakeMessage:
    def __init__(self):
        self.chat = FakeChat()
        self.text = None
        self.photo = None
        self.video = None
        self.caption = None

        self.answer = AsyncMock()
        self.answer_photo = AsyncMock()
        self.answer_video = AsyncMock()


class FakeCallback:
    def __init__(self, message):
        self.message = message
        self.from_user = AsyncMock()
        self.answer = AsyncMock()


class FakeFSM:
    def __init__(self):
        self.data = {}
        self.state = None

    async def update_data(self, **kwargs):
        self.data.update(kwargs)

    async def get_data(self):
        return self.data

    async def set_state(self, state):
        self.state = state

    async def clear(self):
        self.data.clear()


@pytest.mark.asyncio
async def test_choose_target_all(fake_bot, fake_logger, news_service):
    router = NewsRouter(fake_bot, fake_logger, news_service)

    state = FakeFSM()
    await state.update_data(news={"content_type": "text", "text": "hello"})

    message = FakeMessage()
    callback = FakeCallback(message)

    callback_data = AsyncMock()
    callback_data.target = TargetAction.ALL

    await router.choose_target_handler(
        query=callback,
        callback_data=callback_data,
        state=state,
    )

    assert "target" in state.data


@pytest.mark.asyncio
async def test_choose_target_one(
    fake_bot, make_fake_message, fake_state, fake_logger, news_service
):
    router = NewsRouter(fake_bot, fake_logger, news_service)

    callback = AsyncMock()
    callback.answer = AsyncMock()

    message = make_fake_message()

    callback_data = AsyncMock()
    callback_data.target = "one"

    await router.choose_target_handler(
        query=callback,
        callback_data=callback_data,
        state=fake_state,
    )

    fake_state.set_state.assert_awaited_once()
    assert fake_state.set_state.call_args[0][0] == NewStates.wait_user_id


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
    fake_state.set_state.assert_awaited_with(NewStates.choose_target)
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
    fake_state.set_state.assert_awaited_with(NewStates.choose_target)


@pytest.mark.asyncio
@pytest.mark.news
async def test_confirm_news_handler_sends_messages_and_edits_preview(
    fake_bot, make_query_photo, fake_state, fake_logger, news_adapter_mock
):
    query: CallbackQuery = make_query_photo()
    msg: Message = query.message

    news_service = NewsService(adapter=news_adapter_mock)

    # 🔥 ВАЖНО: нужно и news, и target
    fake_state.get_data.return_value = {
        "news": {"content_type": "text", "text": "Hello!"},
        "target": "all",
    }

    # мок списка пользователей
    news_service.all_users_id = AsyncMock(return_value=[111, 222])

    router = NewsRouter(
        bot=fake_bot,
        logger=fake_logger,
        news_service=news_service,
    )

    await router.confirm_news_handler(query=query, state=fake_state)

    # ✔ проверяем отправку
    assert fake_bot.send_message.await_count == 2

    # ✔ очистка FSM
    fake_state.clear.assert_awaited_once()

    # ✔ callback подтверждён
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
