import asyncio

from loguru import logger

from bot.vpn.utils.amnezia_exceptions import AmneziaSSHError
from bot.vpn.utils.ssh_transport import AsyncContainerShellClient


class AsyncDockerSSHClient(AsyncContainerShellClient):
    """Асинхронный клиент для выполнения команд в Docker-контейнере.

    Транспорт (подключение, выполнение команд) — в `AsyncContainerShellClient`,
    здесь только `restart_container`.
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
