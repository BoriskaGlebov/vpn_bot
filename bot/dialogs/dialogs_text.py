# TODO Надо как то в приветсвии писать кома можно написать за помощью сразу
# TODO проверить ссылки на програмки
from pathlib import Path
from pprint import pprint
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


# TODO документация
def extract_knowledge_chunks(data: Any, parent_key: str = "") -> list[dict]:
    """
    Рекурсивно извлекает смысловые текстовые блоки
    для последующей генерации эмбеддингов.
    """
    chunks = []

    if isinstance(data, dict):
        for key, value in data.items():
            new_key = f"{parent_key}.{key}" if parent_key else key
            chunks.extend(extract_knowledge_chunks(value, new_key))

    elif isinstance(data, list):
        if all(isinstance(i, str) for i in data):
            content = "\n".join(data).strip()

            if len(content) > 100:
                chunks.append(
                    {
                        "source": parent_key,
                        "content": content,
                    }
                )
        else:
            for item in data:
                chunks.extend(extract_knowledge_chunks(item, parent_key))

    elif isinstance(data, str):
        if len(data) > 150:
            chunks.append(
                {
                    "source": parent_key,
                    "content": data.strip(),
                }
            )

    return chunks


dialogs = load_dialogs()
chunks = extract_knowledge_chunks(dialogs)
