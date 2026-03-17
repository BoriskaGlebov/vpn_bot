from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bot.config import settings_db
from shared.db.base import Base, int_pk


class KnowledgeChunk(Base):
    """Модель для хранения смысловых текстовых блоков (чанков) с эмбеддингами.

    Attributes
        id (int): Первичный ключ записи.
        source (str): Источник текста, например, имя YAML-файла или документа.
        content (str): Текст чанка, который будет индексироваться.
        embedding (List[float]): Эмбеддинг текста, вектор фиксированной размерности.

    """

    id: Mapped[int_pk]
    source: Mapped[str] = mapped_column(String, nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(settings_db.embedding_dim)
    )  # 768 для intfloat/multilingual-e5-base
    # 256 для intfloat/multilingual-e5-small
    meta: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    __table_args__ = (
        Index(
            "knowledge_chunk_embedding_idx",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 10},  # для маленькой базы
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
