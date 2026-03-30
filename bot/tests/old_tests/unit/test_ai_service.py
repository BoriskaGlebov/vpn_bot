from unittest.mock import AsyncMock

import pytest

from bot.ai.services.service import ChatService


@pytest.mark.asyncio
async def test_is_valid_question_short():
    rag = AsyncMock()
    service = ChatService(rag)
    # question with less than 3 words
    res = await service.ask("Hi there")
    assert res == "Напишите подробнее, не могу понять что вы хотите."


@pytest.mark.asyncio
async def test_ask_calls_rag_chain_and_returns_answer():
    expected = "This is the answer from RAG"
    rag = AsyncMock()
    rag.run = AsyncMock(return_value=expected)
    service = ChatService(rag)

    res = await service.ask("Please explain how to configure vpn")
    assert res == expected
    rag.run.assert_awaited_once_with("Please explain how to configure vpn")


@pytest.mark.asyncio
async def test_ask_propagates_exception_and_logs():
    rag = AsyncMock()

    async def raise_exc(_):
        raise RuntimeError("rag failed")

    rag.run = AsyncMock(side_effect=raise_exc)
    service = ChatService(rag)

    with pytest.raises(RuntimeError):
        await service.ask("Please explain how to configure vpn")
