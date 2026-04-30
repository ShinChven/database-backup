"""MySQL backup using mysqldump; verification via file-size and trailer check."""

from __future__ import annotations

import subprocess
from pathlib import Path

from src.backup.base import BackupJob
from src.config import InstanceConfig, SchemaConfig
from src.logger import get_logger
from src.storage.s3 import S3Storage

log = get_logger(__name__)

_MIN_DUMP_BYTES = 1024        # A valid dump should be at least 1 KB
_TRAILER_MARKER = "-- Dump completed"


class MySQLBackupJob(BackupJob):
    def __init__(self, instance: InstanceConfig, schema: SchemaConfig, storage: S3Storage):
        super().__init__(instance, schema, storage)

    def dump(self, dest: Path) -> None:
        cmd = [
            "mysqldump",
            f"--host={self.instance.host}",
            f"--port={self.instance.port}",
            f"--user={self.instance.user}",
            f"--password={self.instance.password}",
            "--single-transaction",
            "--routines",
            "--triggers",
            "--result-file", str(dest),
            self.schema.name,
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"mysqldump failed for {self.instance.name}/{self.schema.name}: "
                f"{result.stderr.strip()}"
            )

    def verify(self, path: Path) -> None:
        """Check file size and confirm mysqldump trailer is present."""
        if not path.exists():
            raise RuntimeError(f"Dump file missing: {path}")

        size = path.stat().st_size
        if size < _MIN_DUMP_BYTES:
            raise RuntimeError(
                f"Dump file too small ({size} bytes) for "
                f"{self.instance.name}/{self.schema.name}"
            )

        # Read the last 512 bytes to find the completion marker
        with path.open("rb") as f:
            f.seek(max(0, size - 512))
            tail = f.read().decode(errors="replace")

        if _TRAILER_MARKER not in tail:
            raise RuntimeError(
                f"Dump trailer '{_TRAILER_MARKER}' not found in "
                f"{self.instance.name}/{self.schema.name} — dump may be truncated."
            )

        log.info(
            "Verification passed (size + trailer check)",
            extra={"instance": self.instance.name, "schema": self.schema.name, "bytes": size},
        )
