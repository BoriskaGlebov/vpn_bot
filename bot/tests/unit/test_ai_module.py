from unittest.mock import AsyncMock, MagicMock

import pytest
from ai.services.service import ChatService

from bot.ai.dao import KnowledgeChunkDAO
from bot.ai.models import KnowledgeChunk


class DummyRow:
    def __init__(self, doc, distance):
        self.doc = doc
        self.distance = distance

    def __iter__(self):
        # allow unpacking like: for doc, dist in rows
        return iter((self.doc, self.distance))


@pytest.mark.asyncio
class TestKnowledgeChunkDAO:
    async def test_search_by_embedding_validates_input(self, session):
        with pytest.raises(ValueError):
            await KnowledgeChunkDAO.search_by_embedding(
                session=session, query_vector=[], top_k=5, threshold=0.2
            )
        with pytest.raises(ValueError):
            await KnowledgeChunkDAO.search_by_embedding(
                session=session, query_vector=[1.0, None, 3.0], top_k=5, threshold=0.2
            )
        with pytest.raises(ValueError):
            await KnowledgeChunkDAO.search_by_embedding(
                session=session, query_vector=["a", 2.0], top_k=5, threshold=0.2
            )

    async def test_search_by_embedding_filters_by_threshold_and_skips_bad_distances(
        self, monkeypatch
    ):
        # Prepare a fake session where execute(query).all() returns rows of (doc, distance)
        fake_session = MagicMock()

        d1 = KnowledgeChunk()  # content needed for debug logs and return value
        d1.content = "first content"
        d1.source = "src1"
        d2 = KnowledgeChunk()
        d2.content = "second content"
        d2.source = "src2"
        d3 = KnowledgeChunk()
        d3.content = "third content"
        d3.source = "src3"
        d4 = KnowledgeChunk()
        d4.content = "fourth content"
        d4.source = "src4"

        rows = [
            (d1, 0.15),  # keep (< 0.2)
            (d2, 0.25),  # drop (>= 0.2)
            (d3, None),  # skip invalid
            (d4, "bad"),  # skip invalid
        ]

        fake_result = MagicMock()
        fake_result.all.return_value = rows
        fake_session.execute = AsyncMock(return_value=fake_result)

        # Monkeypatch logger to avoid noisy output
        import bot.ai.dao as dao_module

        monkeypatch.setattr(dao_module, "logger", MagicMock())

        res = await KnowledgeChunkDAO.search_by_embedding(
            session=fake_session, query_vector=[0.1, 0.2], top_k=5, threshold=0.2
        )

        assert res == [d1]
        fake_session.execute.assert_awaited()


@pytest.mark.asyncio
class TestChatService:
    async def test_short_question_returns_hint(self, session):
        llm = AsyncMock()
        emb = AsyncMock()
        service = ChatService(llm=llm, emb_service=emb)

        msg = await service.ask("hi?", session)
        assert msg == "Напишите подробнее, не могу понять что вы хотите."
        llm.generate.assert_not_called()
        emb.encode_query.assert_not_called()

    async def test_builds_context_and_calls_llm(self, monkeypatch, session):
        # Arrange mocks
        llm = AsyncMock()
        llm.generate = AsyncMock(return_value="Answer")
        emb = AsyncMock()
        emb.encode_query = AsyncMock(return_value=[0.1, 0.2, 0.3])

        # Provide 3 docs whose combined content exceeds max_context_chars to test cutoff
        docs = []
        d1 = KnowledgeChunk()
        d1.content = "A" * 50
        docs.append(d1)
        d2 = KnowledgeChunk()
        d2.content = "B" * 50
        docs.append(d2)
        d3 = KnowledgeChunk()
        d3.content = "C" * 200
        docs.append(d3)

        async def fake_search_by_embedding(session, query_vector, top_k, threshold):
            return docs

        # Patch DAO method used internally by service
        monkeypatch.setattr(
            KnowledgeChunkDAO,
            "search_by_embedding",
            staticmethod(fake_search_by_embedding),
        )

        # Also mute noisy logs
        import ai.services.service as service_module

        monkeypatch.setattr(service_module, "logger", MagicMock())

        service = ChatService(llm=llm, emb_service=emb)

        # Act: limit total context to 120 chars => 50 + 50 + 20 from the third doc
        answer = await service.ask(
            question="Как подключиться к VPN сервису?",
            session=session,
            max_context_chars=120,
        )

        # Assert final answer and that LLM was called with trimmed context
        assert answer == "Answer"
        assert llm.generate.await_count == 1
        called_ctx = llm.generate.await_args.kwargs["context"]
        assert (
            len(called_ctx.replace("\n\n", "")) == 120
        )  # after join, total raw chars equals limit
        assert called_ctx.startswith("A" * 50 + "\n\n" + "B" * 50)

    async def test_merges_user_history_with_base_context(self, monkeypatch, session):
        llm = AsyncMock()
        llm.generate = AsyncMock(return_value="Final")
        emb = AsyncMock()
        emb.encode_query = AsyncMock(return_value=[0.1])

        d = KnowledgeChunk()
        d.content = "context text"

        async def fake_search_by_embedding(session, query_vector, top_k, threshold):
            return [d]

        monkeypatch.setattr(
            KnowledgeChunkDAO,
            "search_by_embedding",
            staticmethod(fake_search_by_embedding),
        )

        service = ChatService(llm=llm, emb_service=emb)

        history = ["Q1?", "Q2?"]
        await service.ask(
            question="Как оплатить впн?",
            session=session,
            user_context=history,
            max_context_chars=1000,
        )

        called_ctx = llm.generate.await_args.kwargs["context"]
        # Ensure both history marker and base context are present
        assert "Предыдущие вопросы от пользователя" in called_ctx
        assert "Q1?" in called_ctx and "Q2?" in called_ctx
        assert "Данные из базы знаний:" in called_ctx
        assert "context text" in called_ctx

    async def test_llm_empty_answer_returns_fallback(self, monkeypatch, session):
        llm = AsyncMock()
        llm.generate = AsyncMock(return_value="   \n  ")
        emb = AsyncMock()
        emb.encode_query = AsyncMock(return_value=[0.1])

        d = KnowledgeChunk()
        d.content = "some context"

        async def fake_search_by_embedding(session, query_vector, top_k, threshold):
            return [d]

        monkeypatch.setattr(
            KnowledgeChunkDAO,
            "search_by_embedding",
            staticmethod(fake_search_by_embedding),
        )

        service = ChatService(llm=llm, emb_service=emb)
        res = await service.ask(
            "Нормальный вопрос с достаточной длиной", session=session
        )
        assert res == "Не удалось сгенерировать ответ по контексту."

    async def test_propagates_embedding_or_dao_errors(self, monkeypatch, session):
        # Error from emb_service.encode_query
        llm = AsyncMock()
        emb = AsyncMock()
        emb.encode_query = AsyncMock(side_effect=RuntimeError("emb error"))
        service = ChatService(llm=llm, emb_service=emb)

        with pytest.raises(RuntimeError):
            await service.ask("Достаточно длинный вопрос для проверки", session=session)

        # Error from DAO
        emb.encode_query = AsyncMock(return_value=[0.1])

        async def failing_search(*args, **kwargs):
            raise RuntimeError("dao error")

        monkeypatch.setattr(
            KnowledgeChunkDAO, "search_by_embedding", staticmethod(failing_search)
        )

        with pytest.raises(RuntimeError):
            await service.ask("Ещё один валидный вопрос для проверки", session=session)
