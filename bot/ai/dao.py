from bot.ai.models import KnowledgeChunk
from bot.dao.base import BaseDAO


class KnowledgeChunkDAO(BaseDAO[KnowledgeChunk]):
    model = KnowledgeChunk
