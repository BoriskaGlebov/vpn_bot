from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bot.database import Base, int_pk


class KnowledgeChunk(Base):
    """Модель для хранения смысловых текстовых блоков (чанков) с эмбеддингами.

    Attributes
        id (int): Первичный ключ записи.
        source (str): Источник текста, например, имя YAML-файла или документа.
        content (str): Текст чанка, который будет индексироваться.
        embedding (List[float]): Эмбеддинг текста, вектор фиксированной размерности.

    """

    id: Mapped[int_pk]
    source: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(768)
    )  # 768 для intfloat/multilingual-e5-base
