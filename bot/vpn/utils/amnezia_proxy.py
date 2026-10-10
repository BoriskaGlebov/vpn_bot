import asyncio
import shlex

from loguru import logger

from bot.vpn.utils.amnezia_exceptions import AmneziaSSHError
from bot.vpn.utils.ssh_transport import AsyncContainerShellClient


class AsyncDockerSSHClient(AsyncContainerShellClient):
    """Асинхронный клиент для выполнения команд в Docker-контейнере.

    Транспорт (подключение, выполнение команд) — в `AsyncContainerShellClient`,
    здесь только `restart_container`, специфичный для прокси.
    """

    async def restart_container(self) -> bool:
        """Перезапускает Docker-контейнер.

        Returns
            bool: True если контейнер успешно перезапущен.

        Raises
            AmneziaSSHError: Если соединение не установлено (удалённый режим)
                либо команда перезапуска завершилась ошибкой.

        """
        cmd = f"docker restart {self.container}"
        if self.use_local:
            # Host-level команда через подпроцесс, а не Docker SDK: тот
            # синхронный, и container.restart() блокировал бы event loop
            # бота на всё время перезапуска (секунды).
            process = await asyncio.create_subprocess_exec(
                "docker",
                "restart",
                self.container,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            raw_stdout, raw_stderr = await process.communicate()
            stdout, stderr, code = (
                raw_stdout.decode().strip(),
                raw_stderr.decode().strip(),
                process.returncode,
            )
        else:
            if self._conn is None:
                raise AmneziaSSHError(
                    message="AsyncSSH: соединение не установлено. Вызови connect()",
                    cmd=cmd,
                )
            result = await self._conn.run(cmd)
            stdout, stderr, code = (
                str(result.stdout),
                str(result.stderr),
                result.exit_status,
            )

        if code == 0:
            logger.success(f"Контейнер {self.container} успешно перезапущен")
            return True

        raise AmneziaSSHError(
            message="Ошибка при перезапуске контейнера",
            cmd=cmd,
            stdout=str(stdout),
            stderr=str(stderr),
        )


class AmneziaProxy:
    """Сервис управления пользователями 3proxy внутри Docker-контейнера.

    Работает через AsyncDockerSSHClient и выполняет команды
    непосредственно внутри контейнера.
    """

    CONF_DIR = "/usr/local/3proxy/conf"
    USER_FILE = "users.txt"

    def __init__(self, client: AsyncDockerSSHClient, port: str = "433") -> None:
        self.client = client
        self.port = port

    async def _check_container(self) -> bool:
        """Проверяет доступность контейнера.

        Returns
           bool: True, если контейнер доступен и команда `whoami` вернула "root".

        Raises
            AmneziaSSHError: Если контейнер недоступен или команда не вернула "root".

        """
        return await self.client._check_container()

    def _build_tg_link(self, username: str, password: str) -> str:
        """Формирует Telegram socks-ссылку."""
        return (
            f"https://t.me/socks?"
            f"server={self.client.host}"
            f"&port={self.port}"
            f"&user={username}"
            f"&pass={password}"
        )

    async def add_user(self, username: str, password: str) -> str:
        """Добавляет пользователя в users.txt 3proxy.

        Строка добавляется в формате:
            username:CL:password

        Args:
            username: Имя пользователя (без символа ':').
            password: Пароль пользователя (без символа ':').

        Returns
            str: если пользователь успешно добавлен ссылку на прокси

        Raises
            ValueError: Если username или password содержат ':'.
            AmneziaSSHError: Если произошла ошибка при записи в файл.

        """
        if ":" in username or ":" in password:
            raise ValueError("Username и password не должны содержать ':'")

        user_file = f"{self.CONF_DIR}/{self.USER_FILE}"
        line = f"{username}:CL:{password}"

        check_cmd = f"grep '^{shlex.quote(username)}:' {user_file}"
        stdout, _, exit_code, _ = await self.client.write_single_cmd(check_cmd)

        if exit_code == 0:
            try:
                existing_password = stdout.strip().split(":")[2]
            except (IndexError, ValueError) as e:
                raise AmneziaSSHError(
                    message="Некорректный формат строки пользователя",
                    cmd=check_cmd,
                    stdout=stdout,
                    stderr="",
                ) from e

            logger.info(f"Пользователь {username} уже существует")
            return self._build_tg_link(username, existing_password)

        append_cmd = f"echo {shlex.quote(line)} >> {user_file}"
        stdout, stderr, code, cmd = await self.client.write_single_cmd(append_cmd)
        if code == 0:
            logger.success(f"Пользователь {username} успешно добавлен")
            await self.client.restart_container()
            return self._build_tg_link(username, password)

        raise AmneziaSSHError(
            message="Ошибка при добавлении пользователя",
            cmd=cmd,
            stdout=stdout,
            stderr=stderr,
        )

    async def delete_user(self, username: str) -> bool:
        """Удаляет пользователя из users.txt по имени.

        Удаляется строка, начинающаяся с:
            username:

        Args:
            username: Имя пользователя для удаления.

        Returns
            True: если пользователь успешно удалён.
            False: если пользователь не найден.

        Raises
            ValueError: Если username содержит ':'.
            AmneziaSSHError: Если произошла ошибка при модификации файла.

        """
        if ":" in username:
            raise ValueError("Username не должен содержать ':'")

        user_file = f"{self.CONF_DIR}/{self.USER_FILE}"

        check_cmd = f"grep -q '^{shlex.quote(username)}:' {user_file}"
        _, _, exit_code, _ = await self.client.write_single_cmd(check_cmd)

        if exit_code != 0:
            logger.warning("Пользователь не найден")
            return False

        delete_cmd = f"sed -i '/^{shlex.quote(username)}:/d' {user_file}"
        stdout, stderr, code, cmd = await self.client.write_single_cmd(delete_cmd)

        if code == 0:
            logger.success(f"Пользователь {username} удалён")
            await self.client.restart_container()
            return True

        raise AmneziaSSHError(
            message="Ошибка при удалении пользователя",
            cmd=cmd,
            stdout=stdout,
            stderr=stderr,
        )

    async def reload_3proxy(self) -> bool:
        """Перезагружает процесс 3proxy без остановки контейнера.

        Отправляет сигнал HUP процессу 3proxy для перечитывания конфигурации.

        Returns
            True: если reload выполнен успешно.

        Raises
            AmneziaSSHError: Если сигнал не был отправлен или команда завершилась с ошибкой.

        """
        cmd = "pkill -HUP 3proxy"
        stdout, stderr, code, _ = await self.client.write_single_cmd(cmd)

        if code == 0:
            logger.success("3proxy успешно перезагружен")
            return True

        raise AmneziaSSHError(
            message="Ошибка при reload 3proxy",
            cmd=cmd,
            stdout=stdout,
            stderr=stderr,
        )
