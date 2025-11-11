import asyncio
import base64
from pathlib import Path

import aiofiles

from bot.vpn.utils.amnezia_wg import AsyncSSHClientWG


class AsyncSSHClientVPN(AsyncSSHClientWG):
    """Асинхронный SSH-клиент с поддержкой работы через Docker-контейнер.

    Производит генерацию нового конфиг файла в формате для добавления в
    приложение amneziaVPN

    Args:
        host (str): Адрес сервера (IP или DNS).
        username (str): Имя пользователя.
        port (int, optional): SSH-порт. По умолчанию 22.
        key_filename (Optional[str], optional): Путь к приватному ключу.
            Если None, будут использоваться ключи из ``~/.ssh``.
        known_hosts (Optional[str], optional): Путь к файлу ``known_hosts``.
            Если None, проверка отключается.
        container (str, optional): Имя контейнера Docker, в котором
            будут выполняться команды. По умолчанию "amnezia-awg".

    """

    def __init__(
        self,
        host: str,
        username: str,
        port: int = 22,
        key_filename: str | None = None,
        known_hosts: str | None = None,
        container: str = "amnezia-awg",
    ) -> None:
        super().__init__(host, username, port, key_filename, known_hosts, container)

    async def _save_wg_config(
        self,
        filename: str,
        new_ip: str,
        private_key: str,
        pub_server_key: str,
        preshared_key: str,
    ) -> Path:
        """Создает и сохраняет пользовательский конфиг для AmneziaVPN.

        Args:
            filename (str): Название файла конфигурации.
            new_ip (str): IP-адрес пользователя.
            private_key (str): Приватный ключ пользователя.
            pub_server_key (str): Публичный ключ сервера.
            preshared_key (str): PSK ключ сервера.

        Returns
            bool: True, если конфиг создан

        """
        config_text = await self._generate_wg_config(
            new_ip, private_key, pub_server_key, preshared_key
        )
        encode_conf = base64.b64encode(config_text.encode()).decode()
        file_dir = Path(__file__).resolve().parent / "user_cfg"
        file_dir.mkdir(parents=True, exist_ok=True)
        if filename.rsplit(".", 1)[-1] == "vpn":
            file_cfg = file_dir / filename
        else:
            file_cfg = file_dir / f"{filename}.vpn"

        async with aiofiles.open(file_cfg, "w") as f:
            await f.write("vpn://\n")
            await f.write(encode_conf)

        return file_cfg


if __name__ == "__main__":
    """Пример использования AsyncSSHClient."""
    key_path = Path().home() / ".ssh" / "test_vpn"

    async def main() -> None:
        """Пример использования AsyncSSHClient."""
        async with AsyncSSHClientVPN(
            host="help-blocks.ru",
            username="vpn_user",
            key_filename=key_path.as_posix(),
            known_hosts=None,  # Отключить проверку known_hosts
            container="amnezia-awg",
        ) as ssh_client:
            await ssh_client.add_new_user_gen_config("boris456.vpn")
            # await ssh_client.full_delete_user(
            #     "EbXGP3l+Mz6q6huezEfmNr5AKjLcVBDfy+wfAQ2tFHY="
            # )
            await ssh_client.connect()

    asyncio.run(main())
