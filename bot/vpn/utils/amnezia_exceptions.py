class AmneziaError(Exception):
    """Базовый класс для всех ошибок Amnezia.

    Args:
        message (str): Описание ошибки.
        cause (Optional[Exception]): Исходное исключение, если это обертка.

    """

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause

    def __str__(self) -> str:
        """Возвращает строковое представление ошибки, включая причину, если она есть."""
        base = super().__str__()
        details = self._format_details()
        return f"{base}{details}" if details else base

    def _format_details(self) -> str | None:
        """Форматирует дополнительные сведения об ошибке.

        Returns
            str: Строка с подробной информацией об ошибке.
            Если деталей нет, возвращается пустая строка.

        """
        pass


class AmneziaSSHError(AmneziaError):
    """Ошибка при работе с SSH.

    Args:
        message (str): Описание ошибки.
        cmd (str): Команда, которая вызвала ошибку.
        stdout (str): Стандартный вывод команды.
        stderr (str): Стандартный поток ошибок команды.
        cause (Optional[Exception]): Исходное исключение, если это обертка.

    """

    def __init__(
        self,
        message: str,
        cmd: str = "",
        stdout: str = "",
        stderr: str = "",
        *,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, cause=cause)
        self.cmd = cmd
        self.stdout = stdout
        self.stderr = stderr

    def _format_details(self) -> str:
        parts = []

        if self.cmd:
            parts.append(f"Команда: {self.cmd}")
        if self.stdout:
            parts.append(f"stdout: {self.stdout}")
        if self.stderr:
            parts.append(f"stderr: {self.stderr}")
        return "\n" + "\n".join(parts) if parts else ""


class AmneziaConfigError(AmneziaError):
    """Ошибка работы с конфигурацией WireGuard или clientsTable.

    Args:
        message (str): Описание ошибки.
        file (str): Путь к файлу, где произошла ошибка.
        cause (Optional[Exception]): Исходное исключение, если это обертка.

    """

    def __init__(
        self,
        message: str,
        file: str = "",
        *,
        stderr: str = "",
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message, cause=cause)
        self.file = file
        self.stderr = stderr

    def _format_details(self) -> str:
        parts = []

        if self.file:
            parts.append(f"Файл: {self.file}")
        if self.stderr:
            parts.append(f"stderr: {self.stderr}")
        return "\n" + "\n".join(parts) if parts else ""


class AmneziaUserError(AmneziaError):
    """Ошибка связанная с пользователем (добавление/удаление).

    Args:
        message (str): Описание ошибки.
        user (str): Имя пользователя, к которому относится ошибка.
        cause (Optional[Exception]): Исходное исключение, если это обертка.

    """

    def __init__(
        self, message: str, user: str = "", *, cause: Exception | None = None
    ) -> None:
        super().__init__(message, cause=cause)
        self.user = user

    def _format_details(self) -> str:
        parts = []
        if self.user:
            parts.append(f"user: {self.user}")
        return "\n" + "\n".join(parts) if parts else ""
