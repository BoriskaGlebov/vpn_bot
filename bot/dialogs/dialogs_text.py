from pathlib import Path
from pprint import pprint

import yaml
from loguru import logger


def load_dialogs(
    filename=Path(__file__).resolve().parent / "dialog_messages.yaml",
) -> dict:
    """Загрузка базовых настроек диалогов Бота.

    Args:
        filename: путь в конфиг файлу по умолчанию dialog_messages.yaml.

    Returns словарь диалогов.

    """
    try:
        with open(filename, "r", encoding="utf-8") as f:
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

    return data["bot"]


dialogs = load_dialogs()

if __name__ == "__main__":
    pprint(dialogs["general"]["echo"].format(text="test"))
