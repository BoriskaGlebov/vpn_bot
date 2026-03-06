from pathlib import Path
from typing import Any

import yaml
from box import Box
from loguru import logger


def load_dialogs(filename: Path | str | None = None) -> Box:
    """Загружает YAML-файл с диалогами, подставляет шаблоны и возвращает результат как Box (доступ через точку).

    Args:
        filename: Путь к YAML-файлу. Если None — dialog_messages.yaml в текущей папке.

    Returns
        Box: Данные диалогов с доступом через точку.

    Raises
        FileNotFoundError: Если файл не найден.
        KeyError: Если ключ 'bot' отсутствует.

    """
    filename = Path(filename or Path(__file__).parent / "dialog_messages.yaml")

    if not filename.exists():
        logger.error(f"Файл диалогов не найден: {filename}")
        raise FileNotFoundError(filename)

    with filename.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if "bot" not in data:
        logger.warning(f"Ключ 'bot' отсутствует в файле {filename}")
        # return {}
        raise KeyError(f"Ключ 'bot' отсутствует в файле {filename}")

    bot_data = data["bot"]
    templates = bot_data.get("templates", {})

    def substitute_templates(value: Any) -> Any:
        """Рекурсивно подставляет шаблоны в строки и словари."""
        if isinstance(value, str):
            for key, template_text in templates.items():
                # только если есть {ключ} в строке
                if f"{{{key}}}" in value:
                    value = value.replace(f"{{{key}}}", template_text)
            return value
        elif isinstance(value, dict):
            return {k: substitute_templates(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [substitute_templates(v) for v in value]
        return value

    processed_data = {
        k: substitute_templates(v) for k, v in bot_data.items() if k != "templates"
    }

    logger.debug(f"✅ Загружены диалоги из {filename}")
    return Box(processed_data, default_box=True, default_box_attr=None)


def extract_knowledge_chunks(
    data: Any,
    parent_key: str = "",
    *,
    min_list_length: int = 100,
    min_str_length: int = 150,
) -> list[dict[str, str]]:
    """Рекурсивно извлекает смысловые текстовые блоки для генерации эмбеддингов.

    Функция обходит вложенную структуру (dict / list / str) и формирует
    список текстовых фрагментов (чанков), пригодных для индексирования
    в векторной базе.

    Правила извлечения:
        - dict: рекурсивный обход значений.
        - list[str]: объединяется через перенос строки и добавляется,
          если длина итоговой строки >= min_list_length.
        - list[mixed]: рекурсивный обход элементов.
        - str: добавляется как отдельный чанк,
          если длина строки >= min_str_length.

    Для каждого чанка формируется словарь:
        {
            "source": <иерархический путь ключей через точку>,
            "content": <текст чанка>
        }

    Args:
        data: Произвольная вложенная структура данных.
        parent_key: Иерархический путь (через точку),
            используется для формирования поля "source".
        min_list_length: Минимальная длина текста (в символах)
            для списка строк.
        min_str_length: Минимальная длина строки (в символах)
            для добавления как отдельного чанка.

    Returns
        Список словарей с ключами "source" и "content".

    Raises
        Исключения не выбрасываются. Неподдерживаемые типы
        данных игнорируются.

    """
    chunks: list[dict[str, str]] = []

    if isinstance(data, dict):
        logger.debug("Обход словаря: {}", parent_key or "<root>")
        for key, value in data.items():
            new_key = f"{parent_key}.{key}" if parent_key else key
            chunks.extend(
                extract_knowledge_chunks(
                    value,
                    new_key,
                    min_list_length=min_list_length,
                    min_str_length=min_str_length,
                )
            )
        logger.debug(" ✅  Чанки получены из словаря с инструкциями")

    elif isinstance(data, list):
        logger.debug(
            "Обработка списка: '{}' (элементов: {})",
            parent_key or "<root>",
            len(data),
        )

        if all(isinstance(i, str) for i in data):
            content = "\n".join(data).strip()

            if len(content) >= min_list_length:
                chunks.append(
                    {
                        "source": parent_key,
                        "content": content,
                    }
                )
            else:
                logger.trace(
                    "Список пропущен (слишком короткий): '{}' (длина: {})",
                    parent_key,
                    len(content),
                )
        else:
            for item in data:
                chunks.extend(
                    extract_knowledge_chunks(
                        item,
                        parent_key,
                        min_list_length=min_list_length,
                        min_str_length=min_str_length,
                    )
                )
        logger.debug(" ✅  Чанки получены из словаря с инструкциями")

    elif isinstance(data, str):
        content = data.strip()

        if len(content) >= min_str_length:
            chunks.append(
                {
                    "source": parent_key,
                    "content": content,
                }
            )
        else:
            logger.trace(
                "Строка пропущена (слишком короткая): '{}' (длина: {})",
                parent_key,
                len(content),
            )

    else:
        logger.trace(
            "Тип данных не поддерживается: '{}' ({})",
            parent_key,
            type(data).__name__,
        )

    return chunks


dialogs = load_dialogs()
chunks = extract_knowledge_chunks(dialogs.instructions_ai)
