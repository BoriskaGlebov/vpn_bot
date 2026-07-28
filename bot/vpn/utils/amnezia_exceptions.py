from bot.app_error.base_error import AppError


class AmneziaError(AppError):
    """Базовый класс для всех ошибок Amnezia.

    Наследуется от `AppError`, чтобы попадать в общий `ErrorHandlerMiddleware`
    (который распознаёт только `AppError`/`APIClientError`) и корректно
    превращаться в `ErrorEnvelope` вместо generic "unexpected_error".

    Args:
        message (str): Описание ошибки.
        cause (Optional[Exception]): Исходное исключение, если это обертка.

    """

    code: str = "amnezia_error"
    status_code: int = 502


class AmneziaSSHError(AmneziaError):
    """Ошибка при работе с SSH.

    Args:
        message (str): Описание ошибки.
        cmd (str): Команда, которая вызвала ошибку.
        stdout (str): Стандартный вывод команды.
        stderr (str): Стандартный поток ошибок команды.
        cause (Optional[Exception]): Исходное исключение, если это обертка.

    """

    code = "amnezia_ssh_error"

    def __init__(
        self,
        message: str,
        *,
        cmd: str = "",
        stdout: str = "",
        stderr: str = "",
        cause: Exception | None = None,
    ) -> None:
        super().__init__(
            message,
            details={
                "cmd": cmd,
                "stdout": stdout,
                "stderr": stderr,
            },
            cause=cause,
        )

        self.cmd = cmd
        self.stdout = stdout
        self.stderr = stderr


class AmneziaConfigError(AmneziaError):
    """Ошибка работы с конфигурацией WireGuard или clientsTable.

    Args:
        message (str): Описание ошибки.
        file (str): Путь к файлу, где произошла ошибка.
        cause (Optional[Exception]): Исходное исключение, если это обертка.

    """

    code = "amnezia_config_error"

    def __init__(
        self,
        message: str,
        *,
        file: str = "",
        stderr: str = "",
        cause: Exception | None = None,
    ) -> None:
        super().__init__(
            message,
            details={
                "file": file,
                "stderr": stderr,
            },
            cause=cause,
        )

        self.file = file
        self.stderr = stderr


class AmneziaUserError(AmneziaError):
    """Ошибка связанная с пользователем (добавление/удаление).

    Args:
        message (str): Описание ошибки.
        user (str): Имя пользователя, к которому относится ошибка.
        cause (Optional[Exception]): Исходное исключение, если это обертка.

    """

    code = "amnezia_user_error"

    def __init__(
        self,
        message: str,
        *,
        user: str = "",
        cause: Exception | None = None,
    ) -> None:
        super().__init__(
            message,
            details={
                "user": user,
            },
            cause=cause,
        )

        self.user = user
