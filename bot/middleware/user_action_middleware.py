# import time
# from typing import Any, Awaitable, Callable
#
# from aiogram import BaseMiddleware
# from aiogram.types import TelegramObject
# from loguru import logger
#
#
# class UserActionLoggingMiddleware(BaseMiddleware):
#     """Middleware для логирования действий пользователя в хэндлерах."""
#
#     def __init__(self, log_data: bool = True, log_time: bool = True):
#         """
#         Args:
#             log_data (bool): логировать данные события (сообщение, callback)
#             log_time (bool): логировать время выполнения хэндлера
#         """
#         super().__init__()
#         self.log_data = log_data
#         self.log_time = log_time
#
#     async def __call__(
#         self,
#         handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
#         event: TelegramObject,
#         data: dict[str, Any],
#     ) -> Any:
#         user_id = (
#             getattr(event.from_user, "id", None)
#             if hasattr(event, "from_user")
#             else None
#         )
#         handler_name = handler.__name__
#
#         # Логируем старт
#         if self.log_data:
#             logger.info(
#                 f"START handler={handler_name}, user_id={user_id}, event={event}"
#             )
#         else:
#             logger.info(f"START handler={handler_name}, user_id={user_id}")
#
#         start_time = time.time()
#
#         try:
#             result = await handler(event, data)
#         finally:
#             elapsed = time.time() - start_time
#             if self.log_data:
#                 logger.info(
#                     f"END handler={handler_name}, user_id={user_id}, elapsed={elapsed:.3f}s, event={event}"
#                 )
#             else:
#                 logger.info(
#                     f"END handler={handler_name}, user_id={user_id}, elapsed={elapsed:.3f}s"
#                 )
#
#         return result
