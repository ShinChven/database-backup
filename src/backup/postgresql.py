"""PostgreSQL backup using pg_dump; verification via pg_restore --list."""

from __future__ import annotations

import subprocess
from pathlib import Path

from src.backup.base import BackupJob
from src.config import InstanceConfig, SchemaConfig
from src.logger import get_logger
from src.storage.s3 import S3Storage

log = get_logger(__name__)


class PostgreSQLBackupJob(BackupJob):
    def __init__(self, instance: InstanceConfig, schema: SchemaConfig, storage: S3Storage):
        super().__init__(instance, schema, storage)

    def _env(self) -> dict:
        """Build environment with PGPASSWORD set."""
        import os
        env = os.environ.copy()
        env["PGPASSWORD"] = self.instance.password
        return env

    def dump(self, dest: Path) -> None:
        cmd = [
            "pg_dump",
            "--host", self.instance.host,
            "--port", str(self.instance.port),
            "--username", self.instance.user,
            "--dbname", self.schema.name,
            "--format", "custom",   # custom format supports pg_restore --list
            "--file", str(dest),
            "--no-password",
        ]
        result = subprocess.run(
            cmd,
            env=self._env(),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"pg_dump failed for {self.instance.name}/{self.schema.name}: "
                f"{result.stderr.strip()}"
            )

    def verify(self, path: Path) -> None:
        """Run pg_restore --list to confirm the dump is a valid custom-format file."""
        if not path.exists() or path.stat().st_size == 0:
            raise RuntimeError(
                f"Dump file missing or empty: {path}"
            )
        result = subprocess.run(
            ["pg_restore", "--list", str(path)],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Dump verification failed for {self.instance.name}/{self.schema.name}: "
                f"{result.stderr.strip()}"
            )
        log.info(
            "Verification passed (pg_restore --list)",
            extra={"instance": self.instance.name, "schema": self.schema.name},
        )
