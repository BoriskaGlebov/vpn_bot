from pathlib import Path
from pprint import pprint
from typing import Any

import yaml
from loguru import logger


def load_dialogs(filename: Path | str | None = None) -> dict[str, Any]:
    """Загружает YAML, подставляет шаблоны и возвращает готовый словарь."""
    filename = Path(filename or Path(__file__).parent / "dialog_messages.yaml")

    if not filename.exists():
        logger.error(f"Файл диалогов не найден: {filename}")
        raise FileNotFoundError(filename)

    with filename.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    if "bot" not in data:
        logger.warning(f"Ключ 'bot' отсутствует в файле {filename}")
        return {}

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

    # создаём новый словарь без templates
    processed_data = {
        k: substitute_templates(v) for k, v in bot_data.items() if k != "templates"
    }

    logger.debug(f"✅ Загружены диалоги из {filename}")
    return processed_data


dialogs = load_dialogs()

if __name__ == "__main__":
    pprint(dialogs["general"]["echo"].format(text="test"))
