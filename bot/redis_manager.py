from bot.config import logger, settings_db
from shared.clients.redis_client import RedisClient

redis_manager = RedisClient(str(settings_db.redis_url), logger=logger)  # type: ignore[arg-type]
