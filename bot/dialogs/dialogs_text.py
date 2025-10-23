from pathlib import Path
from pprint import pprint
from typing import Any, cast

import yaml
from loguru import logger


def load_dialogs(
    filename: Path = Path(__file__).resolve().parent / "dialog_messages.yaml",
) -> dict[str, Any]:
    """Загрузка базовых настроек диалогов Бота.

    Args:
        filename (Path): путь в конфиг файлу по умолчанию dialog_messages.yaml.

    Returns словарь диалогов.

    """
    try:
        with open(filename, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError as e:
        logger.error(f"Файл диалогов не найден: {filename}")
        raise e
    except yaml.YAMLError as e:
        logger.error(f"Ошибка при чтении YAML файла {filename}: {e}")
        raise e

    if "bot" not in data:
        logger.warning(f"Ключ 'bot' отсутствует в файле {filename}")
        raise KeyError("Ключ 'bot' отсутствует в файле {filename}")

    return cast(dict[str, Any], data["bot"])


dialogs = load_dialogs()

if __name__ == "__main__":
    pprint(dialogs["general"]["echo"].format(text="test"))
