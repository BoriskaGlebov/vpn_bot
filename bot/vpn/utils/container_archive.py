import shlex
from asyncio import create_subprocess_exec, subprocess
from dataclasses import dataclass
from datetime import UTC, datetime

import aioboto3
import asyncssh
from aiobotocore.session import ClientCreatorContext
from cryptography.fernet import Fernet, InvalidToken
from pydantic import SecretStr

from bot.core.config import BucketSettings, VPNNode
from bot.vpn.utils.amnezia_exceptions import AmneziaBackupError, AmneziaSSHError

AMNEZIA_DIR = "/opt/amnezia"
AMNEZIA_ENTRIES = ("awg", "start.sh")
S3_BACKUP_PREFIX = "backup/containers"


@dataclass(frozen=True)
class BackupObject:
    """Описание архива бэкапа, лежащего в S3.

    Attributes
        key (str): Ключ объекта в S3.
        last_modified (datetime): Время загрузки архива.
        size (int): Размер объекта в байтах.

    """

    key: str
    last_modified: datetime
    size: int


class ContainerArchiveTransport:
    """Упаковывает/распаковывает `/opt/amnezia` Docker-контейнера ноды.

    Скрывает разницу между нодой, совпадающей с хостом запуска скрипта
    (`node.use_local=True`, доступ через локальный `docker exec`), и
    удалённой нодой (доступ по SSH с агентским пробросом ключей).

    Args:
        node (VPNNode): Конфигурация ноды (host, username, container, use_local).

    """

    def __init__(self, node: VPNNode) -> None:
        self._node = node

    async def read_archive(self) -> bytes:
        """Архивирует `/opt/amnezia` контейнера в `tar.gz` и возвращает байты.

        Returns
            bytes: Содержимое архива.

        Raises
            AmneziaSSHError: При ошибке доступа к контейнеру.

        """
        argv = self._docker_exec_argv(
            "tar", "czf", "-", "-C", AMNEZIA_DIR, *AMNEZIA_ENTRIES
        )
        return await self._execute(
            argv, action=f"заархивировать контейнер {self._node.container}"
        )

    async def write_archive(self, data: bytes) -> None:
        """Распаковывает `tar.gz`-архив обратно в `/opt/amnezia` контейнера.

        Args:
            data (bytes): Содержимое архива (уже расшифрованное).

        Raises
            AmneziaSSHError: При ошибке доступа к контейнеру.

        """
        argv = self._docker_exec_argv("tar", "xzf", "-", "-C", AMNEZIA_DIR)
        await self._execute(
            argv, action=f"восстановить контейнер {self._node.container}", stdin=data
        )

    def _docker_exec_argv(self, *cmd: str) -> list[str]:
        return ["docker", "exec", "-i", self._node.container, *cmd]

    async def _execute(
        self, argv: list[str], *, action: str, stdin: bytes | None = None
    ) -> bytes:
        if self._node.use_local:
            return await self._run_local(argv, action=action, stdin=stdin)
        return await self._run_remote(argv, action=action, stdin=stdin)

    async def _run_local(
        self, argv: list[str], *, action: str, stdin: bytes | None
    ) -> bytes:
        process = await create_subprocess_exec(
            *argv,
            stdin=subprocess.PIPE if stdin is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await process.communicate(input=stdin)
        if process.returncode != 0:
            raise AmneziaSSHError(
                message=f"Не удалось {action}",
                cmd=" ".join(argv),
                stderr=stderr.decode(errors="replace"),
            )
        return stdout

    async def _run_remote(
        self, argv: list[str], *, action: str, stdin: bytes | None
    ) -> bytes:
        cmd = " ".join(shlex.quote(arg) for arg in argv)
        try:
            async with asyncssh.connect(
                host=self._node.host,
                username=self._node.username,
                known_hosts=None,
                agent_forwarding=True,
            ) as conn:
                result = await conn.run(cmd, input=stdin, encoding=None)
        except (OSError, asyncssh.Error) as exc:
            raise AmneziaSSHError(
                message=f"Ошибка SSH-подключения к {self._node.host}: {exc}", cmd=cmd
            ) from exc

        if result.exit_status != 0:
            stderr = result.stderr
            raise AmneziaSSHError(
                message=f"Не удалось {action} на {self._node.host}",
                cmd=cmd,
                stderr=(
                    stderr.decode(errors="replace")
                    if isinstance(stderr, bytes)
                    else (stderr or "")
                ),
            )

        return self._as_bytes(result.stdout)

    @staticmethod
    def _as_bytes(value: bytes | str | None) -> bytes:
        if isinstance(value, bytes):
            return value
        return (value or "").encode()


class ArchiveCipher:
    """Шифрует/расшифровывает архивы бэкапа ключом Fernet (AES-128-CBC + HMAC).

    Args:
        key (SecretStr | None): Значение `BACKUP_ENCRYPTION_KEY`
            (`settings_bot.bucket.backup_encryption_key`).

    """

    def __init__(self, key: SecretStr | None) -> None:
        self._key = key

    def encrypt(self, data: bytes) -> bytes:
        """Шифрует данные архива.

        Args:
            data (bytes): Содержимое архива в открытом виде.

        Returns
            bytes: Зашифрованные данные.

        Raises
            AmneziaBackupError: Если ключ шифрования не сконфигурирован.

        """
        return self._fernet().encrypt(data)

    def decrypt(self, data: bytes) -> bytes:
        """Расшифровывает данные архива.

        Args:
            data (bytes): Зашифрованное содержимое архива.

        Returns
            bytes: Содержимое архива в открытом виде.

        Raises
            AmneziaBackupError: Если ключ шифрования не сконфигурирован,
                либо архив зашифрован другим ключом/повреждён.

        """
        try:
            return self._fernet().decrypt(data)
        except InvalidToken as exc:
            raise AmneziaBackupError(
                "Не удалось расшифровать архив: неверный ключ шифрования или архив повреждён"
            ) from exc

    def _fernet(self) -> Fernet:
        if self._key is None:
            raise AmneziaBackupError("Не задан BACKUP_ENCRYPTION_KEY")
        return Fernet(self._key.get_secret_value().encode())


class ContainerBackupStorage:
    """Хранилище архивов бэкапа контейнеров в S3-совместимом бакете.

    Args:
        bucket (BucketSettings): Настройки S3 (`settings_bot.bucket`).

    """

    def __init__(self, bucket: BucketSettings) -> None:
        self._bucket = bucket

    async def upload(self, node_name: str, data: bytes) -> str:
        """Загружает архив ноды в S3 под ключом с текущей меткой времени.

        Args:
            node_name (str): Имя ноды (ключ в `settings_bot.vpn.nodes`).
            data (bytes): Зашифрованные данные архива.

        Returns
            str: Ключ загруженного объекта в S3.

        Raises
            AmneziaBackupError: Если загрузка завершилась ошибкой.

        """
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d_%H-%M-%S")
        key = f"{S3_BACKUP_PREFIX}/{node_name}/{node_name}_{timestamp}.tar.gz.enc"
        try:
            async with self._client() as s3:
                await s3.put_object(Bucket=self._bucket.bucket_name, Key=key, Body=data)
        except Exception as exc:
            raise AmneziaBackupError(
                f"Не удалось загрузить бэкап ноды {node_name} в S3: {exc}", cause=exc
            ) from exc
        return key

    async def download(self, key: str) -> bytes:
        """Скачивает архив из S3 по ключу.

        Args:
            key (str): Ключ объекта в S3.

        Returns
            bytes: Содержимое объекта.

        Raises
            AmneziaBackupError: Если скачивание завершилось ошибкой.

        """
        try:
            async with self._client() as s3:
                response = await s3.get_object(Bucket=self._bucket.bucket_name, Key=key)
                async with response["Body"] as stream:
                    return await stream.read()
        except Exception as exc:
            raise AmneziaBackupError(
                f"Не удалось скачать бэкап {key} из S3: {exc}", cause=exc
            ) from exc

    async def list_backups(self, node_name: str) -> list[BackupObject]:
        """Возвращает архивы ноды в S3, отсортированные от старых к новым.

        Args:
            node_name (str): Имя ноды (ключ в `settings_bot.vpn.nodes`).

        Returns
            list[BackupObject]: Список архивов ноды.

        Raises
            AmneziaBackupError: Если запрос списка завершился ошибкой.

        """
        prefix = f"{S3_BACKUP_PREFIX}/{node_name}/"
        objects: list[BackupObject] = []
        try:
            async with self._client() as s3:
                paginator = s3.get_paginator("list_objects_v2")
                async for page in paginator.paginate(
                    Bucket=self._bucket.bucket_name, Prefix=prefix
                ):
                    for obj in page.get("Contents", []):
                        objects.append(
                            BackupObject(
                                key=obj["Key"],
                                last_modified=obj["LastModified"],
                                size=obj["Size"],
                            )
                        )
        except Exception as exc:
            raise AmneziaBackupError(
                f"Не удалось получить список бэкапов ноды {node_name}: {exc}", cause=exc
            ) from exc
        return sorted(objects, key=lambda obj: obj.last_modified)

    async def latest_backup(self, node_name: str) -> BackupObject | None:
        """Возвращает самый свежий архив ноды.

        Args:
            node_name (str): Имя ноды (ключ в `settings_bot.vpn.nodes`).

        Returns
            BackupObject | None: Самый свежий архив, либо `None`, если их нет.

        """
        backups = await self.list_backups(node_name)
        return backups[-1] if backups else None

    def _client(self) -> ClientCreatorContext:
        session = aioboto3.Session()
        return session.client(
            "s3",
            endpoint_url=self._bucket.endpoint_url,
            aws_access_key_id=self._bucket.access_key.get_secret_value(),
            aws_secret_access_key=self._bucket.secret_key.get_secret_value(),
        )
