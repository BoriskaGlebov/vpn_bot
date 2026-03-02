from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SKnowledgeChunk(BaseModel):
    source: str
    content: str
    embedding: list[float]

    model_config = ConfigDict(from_attributes=True)


class SKnowledgeChunkFilter(BaseModel):
    source: str
