from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from bot.database import Base, int_pk


class KnowledgeChunk(Base):
    id: Mapped[int_pk]
    source: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(512)
    )  # 512 для distiluse-base-multilingual-cased-v2
