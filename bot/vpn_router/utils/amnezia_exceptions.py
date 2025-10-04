class AmneziaError(Exception):
    """Базовый класс для всех ошибок Amnezia.

    Args:
        message (str): Описание ошибки.
        cause (Optional[Exception]): Исходное исключение, если это обертка.

    """

    def __init__(self, message: str, *, cause: Exception | None = None):
        super().__init__(message)
        self.cause = cause

    def __str__(self) -> str:
        """Возвращает строковое представление ошибки, включая причину, если она есть."""
        base = super().__str__()
        if self.cause:
            return f"{base} (из-за: {self.cause})"
        return base


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
    ):
        super().__init__(message, cause=cause)
        self.cmd = cmd
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self) -> str:
        """Возвращает строковое представление ошибки, включая детали команды и выводы."""
        base = super().__str__()
        details = f"\nКоманда: {self.cmd}\nstdout: {self.stdout}\nstderr: {self.stderr}"
        return f"{base}{details}"


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
    ):
        super().__init__(message, cause=cause)
        self.file = file
        self.stderr = stderr

    def __str__(self) -> str:
        """Возвращает строковое представление ошибки, включая путь к файлу и stderr, если они есть."""
        base = super().__str__()
        details = f"\nstderr: {self.stderr}" if self.stderr else ""
        files_inf = f"\nФайл: {self.file}" if self.file else ""
        return f"{base}{files_inf}{details}"


class AmneziaUserError(AmneziaError):
    """Ошибка связанная с пользователем (добавление/удаление).

    Args:
        message (str): Описание ошибки.
        user (str): Имя пользователя, к которому относится ошибка.
        cause (Optional[Exception]): Исходное исключение, если это обертка.

    """

    def __init__(self, message: str, user: str = "", *, cause: Exception | None = None):
        super().__init__(message, cause=cause)
        self.user = user

    def __str__(self) -> str:
        """Возвращает строковое представление ошибки, включая имя пользователя, если оно есть."""
        base = super().__str__()
        return f"{base}\nПользователь: {self.user}" if self.user else base
