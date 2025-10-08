# import asyncio
# import re
#
# from aiogram import Bot
# from aiogram.fsm.context import FSMContext
# from aiogram.fsm.state import State
# from aiogram.types import (
#     CallbackQuery,
#     InlineKeyboardMarkup,
#     Message,
#     ReplyKeyboardMarkup,
#     ReplyKeyboardRemove,
# )
# from aiogram.utils.chat_action import ChatActionSender
#
# from bot.config import logger, settings
# from bot.users.dao import UserDAO
# from bot.users.keyboards.inline_kb import approve_keyboard
# from bot.users.keyboards.markup_kb import phone_kb
# from bot.users.schemas import TelegramIDModel
#
# m_start = settings.MESSAGES["mode"]["start"]
# m_error = settings.MESSAGES["mode"]["error"]
#
#
# def get_refer_id_or_none(command_args: str, user_id: int) -> int | None:
#     """
#     Определяет реферальный ID из аргументов команды.
#
#     Возвращает реферальный ID, если он валиден, или None,
#     если аргументы не соответствуют требованиям (например, если это не число
#     или это ID самого пользователя).
#
#     Args:
#         command_args (str): Аргументы команды, содержащие потенциальный
#         реферальный ID.
#         user_id (int): ID текущего пользователя, чтобы убедиться, что он не
#         пытается использовать свой собственный ID в качестве реферала.
#
#     Returns:
#         int | None: Если аргумент команды является валидным
#         реферальным ID (целое число, больше 0 и не равное user_id),
#                     то возвращается этот ID. Иначе возвращается None.
#
#     """
#     return (
#         int(command_args)
#         if command_args
#         and command_args.isdigit()
#         and int(command_args) > 0
#         and int(command_args) != user_id
#         else None
#     )
#
#
# def normalize_phone_number(phone: str) -> str:
#     """
#     Нормализует номер телефона.
#
#     - Добавляет + перед 7, если его нет.
#     - Если начинается с 8, заменяет на +7.
#     """
#     phone = re.sub(r"\D", "", phone)  # Убираем все нецифровые символы
#
#     if phone.startswith("8") and len(phone) == 11:
#         phone = "+7" + phone[1:]
#     elif phone.startswith("7") and len(phone) == 11:
#         phone = "+7" + phone[1:]
#     elif len(phone) == 10:  # Если пользователь ввел только 10 цифр (без кода страны)
#         phone = "+7" + phone
#
#     return phone if phone.startswith("+") else f"+{phone}"
#
#
# async def mistakes_handler(
#     message: Message,
#     bot: Bot,
#     state: FSMContext,
#     kb: ReplyKeyboardMarkup | InlineKeyboardMarkup = None,
#     answer: str = m_error["correct_choice_up"],
# ) -> None:
#     """
#     Обработчик для случаев, когда пользователь отправляет текст вместо кнопок.
#
#     Этот обработчик вызывается, когда пользователь вводит текст в состоянии анкеты,
#     где ожидается выбор из клавиатуры.
#     Бот информирует пользователя о том, что нужно выбрать одну из кнопок.
#     По умолчанию - Пожалуйста, выберите один из вариантов, нажав на кнопку ВВЕРХ
#
#
#     Args:
#         message (Message): Сообщение от пользователя, содержащее его текст.
#         bot (Bot): Бот, который отправляет сообщения
#         state (FSMContext): Контекст машины состояний, где хранятся данные анкеты.
#         answer (str) : Ответ по умолчанию, но можно выбирать.
#         kb (ReplyKeyboardMarkup): клавиатура для ответа
#
#     Returns:
#         None: Функция не возвращает значений, но отправляет сообщение
#         пользователю о том, что нужно выбрать кнопку.
#
#     """
#     try:
#         # Включаем индикатор набора текста
#         async with ChatActionSender.typing(bot=bot, chat_id=message.chat.id):
#             await asyncio.sleep(0.5)  # Немного подождем, чтобы пользователь видел индикатор
#             # message_id = message.message_id
#             await asyncio.sleep(0.5)
#             await message.delete()
#             # Отправляем сообщение с просьбой выбрать кнопку
#             if kb:
#                 await message.answer(text=answer, reply_markup=kb)
#             else:
#                 await message.answer(text=answer)
#             # await bot.delete_message(chat_id=message.chat.id, message_id=message_id - 1)
#     except Exception as e:
#         # Логируем ошибку
#         logger.error(f"Ошибка при обработке запроса {mistakes_handler.__name__}: {e}")
#         await message.answer(m_error["message_default"])
#
#
# async def age_callback(call: CallbackQuery, state: FSMContext, fsm: State, bot: Bot) -> None:
#     """
#     Обработчик callback-запросов для проверки возраста пользователя.
#
#     Этот обработчик вызывается, когда пользователь отвечает на
#     вопрос о возрасте в анкете.
#     Если пользователь подтвердил, что ему исполнилось 18 лет,
#     он переходит к следующему вопросу.
#     В противном случае, анкета обнуляется, и пользователю отправляется
#     сообщение о том, что
#     он не может воспользоваться услугами.
#
#     Args:
#         call (CallbackQuery): Объект callback-запроса, который
#         содержит данные о взаимодействии пользователя с клавиатурой.
#         state (FSMContext): Контекст машины состояний, в котором хранятся данные анкеты.
#         fsm (StatesGroup): На какое состояние надо поменять
#         bot (Bot): бот
#     Returns:
#         None: Функция не возвращает значения, но отправляет сообщение пользователю.
#
#     """
#     try:
#         await call.answer(text="Проверяю ввод", show_alert=False)
#
#         # Обработка данных из callback
#         approve_inf = call.data.replace("approve_", "")
#         approve_inf = True if approve_inf == "True" else False
#
#         # Удаляем сообщение и клавиатуру с вопросом
#         await call.message.delete()
#
#         # Включаем индикатор набора текста
#         async with ChatActionSender.typing(bot=bot, chat_id=call.message.chat.id):
#             # Если возраст подтвержден, переходим к следующему вопросу
#             if approve_inf:
#                 await state.update_data(age=approve_inf)
#                 await bot.send_message(
#                     chat_id=call.message.chat.id,
#                     text=m_start["citizenship"]["question"],
#                     reply_markup=approve_keyboard("Да", "Нет"),
#                 )
#                 await state.set_state(fsm)
#
#                 # Если возраст не подтвержден, очищаем данные и сообщаем пользователю
#             else:
#                 await state.clear()
#                 await bot.send_message(
#                     chat_id=call.message.chat.id,
#                     text=m_start["age"]["rejection"],
#                 )
#
#     except Exception as e:
#         # Логируем ошибку
#         logger.error(
#             f"Ошибка при обработке запроса {age_callback.__name__} "
#             f"(Обработчик callback-запросов для проверки возраста пользователя.): {e}"
#         )
#         await call.message.answer(m_error["message_default"])
#
#
# async def resident_callback(
#     call: CallbackQuery,
#     state: FSMContext,
#     fsm: list[State],
#     bot: Bot,
#     answer: str,
#     session,
# ) -> None:
#     """
#     Обработчик callback-запросов для проверки налогового резидентства пользователя.
#
#     Этот обработчик вызывается, когда пользователь отвечает на вопрос о
#     налоговом резидентстве в анкете.
#     Если пользователь является налоговым резидентом России, ему
#     показывается основное меню,
#     иначе анкета обнуляется, и пользователю отправляется сообщение о том,
#     что бот не работает с налоговыми резидентами других стран.
#
#     Args:
#         call (CallbackQuery): Объект callback-запроса,
#         который содержит данные о взаимодействии пользователя с клавиатурой.
#         state (FSMContext): Контекст машины состояний, в котором хранятся данные анкеты.
#         fsm (State): На какое состояние надо поменять
#         bot (Bot): бот
#         answer (str): Собственный ответ вопрос для отправки
#         session : асинхронная сессия для БД
#     Returns:
#         None: Функция не возвращает значения, но отправляет сообщение пользователю.
#
#     """
#     try:
#         user_inf = await UserDAO.find_one_or_none(
#             filters=TelegramIDModel(telegram_id=call.from_user.id), session=session
#         )
#         # Ответ на запрос и удаление сообщения
#         await call.answer(text="Проверяю ввод", show_alert=False)
#         approve_inf = call.data.replace("approve_", "")
#         approve_inf = True if approve_inf == "True" else False
#         await call.message.delete()
#
#         # Включаем индикатор набора текста
#         async with ChatActionSender.typing(bot=bot, chat_id=call.message.chat.id):
#             # Логика для резидента
#             if approve_inf and user_inf.phone_number is not None:
#                 await state.update_data(resident=approve_inf)
#                 await bot.send_message(
#                     chat_id=call.message.chat.id,
#                     text=answer,
#                     reply_markup=ReplyKeyboardRemove(),
#                 )
#                 await state.set_state(fsm[0])  # Жду новый вопрос
#             elif approve_inf and user_inf.phone_number is None:
#                 await state.update_data(resident=approve_inf)
#                 await bot.send_message(
#                     chat_id=call.message.chat.id,
#                     text=m_start["phone"]["question"],
#                     reply_markup=phone_kb(),
#                 )
#                 await state.set_state(fsm[1])  # Выбираю добавление номера телефона
#             else:
#                 # Логика для не-резидента
#                 await state.clear()
#                 await bot.send_message(
#                     chat_id=call.message.chat.id,
#                     text=m_start["citizenship"]["rejection"],
#                     reply_markup=ReplyKeyboardRemove(),
#                 )
#     except AttributeError:
#         # Логируем ошибку
#         logger.error("Пользователь еще не добавлен в БД, нужно еще раз нажать СТАРТ")
#         await call.message.answer(m_error["start_again"])
