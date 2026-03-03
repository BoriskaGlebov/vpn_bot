from pydantic import BaseModel, ConfigDict


class SKnowledgeChunk(BaseModel):
    """Схема для представления смыслового текстового блока (чанка) с эмбеддингом.

    Attribute
        source (str): Источник текста, например, имя файла или документа.
        content (str): Текст чанка.
        embedding (List[float]): Эмбеддинг текста в виде списка чисел.

    """

    source: str
    content: str
    embedding: list[float]

    model_config = ConfigDict(from_attributes=True)


class SKnowledgeChunkFilter(BaseModel):
    """Схема фильтра для поиска чанков в базе по источнику.

    Attributes
        source (str): Источник текста для фильтрации.

    """

    source: str
