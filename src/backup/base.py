"""Abstract base class for backup jobs."""

from __future__ import annotations

import gzip
import os
import shutil
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path

from src.config import InstanceConfig, SchemaConfig
from src.logger import get_logger
from src.storage.s3 import S3Storage

log = get_logger(__name__)


class BackupJob(ABC):
    """
    Orchestrates one schema backup:
      dump → verify → upload → retention
    Raises on any unrecoverable step; the scheduler catches and logs.
    """

    def __init__(self, instance: InstanceConfig, schema: SchemaConfig, storage: S3Storage):
        self.instance = instance
        self.schema = schema
        self.storage = storage

    # ── Subclass contract ─────────────────────────────────────────────────────

    # File extension for the uncompressed dump. Subclasses override when the
    # dump is not plain SQL (e.g. pg_dump custom format is a binary archive).
    DUMP_EXTENSION = "sql"

    @abstractmethod
    def dump(self, dest: Path) -> None:
        """Write an uncompressed dump to `dest`. Raise on failure."""

    @abstractmethod
    def verify(self, path: Path) -> None:
        """Verify the dump at `path`. Raise on failure."""

    # ── Shared filename logic ─────────────────────────────────────────────────

    def _filename(self) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"{self.schema.name}_{ts}.{self.DUMP_EXTENSION}.gz"

    # ── Public entry point ────────────────────────────────────────────────────

    def run(self) -> None:
        instance_name = self.instance.name
        schema_name = self.schema.name

        with tempfile.TemporaryDirectory(prefix="dbbackup_") as tmpdir:
            raw_path = Path(tmpdir) / f"{schema_name}.{self.DUMP_EXTENSION}"
            gz_path = Path(tmpdir) / self._filename()

            # 1. Dump
            log.info("Starting dump", extra={"instance": instance_name, "schema": schema_name})
            self.dump(raw_path)

            # 2. Verify (before compression — easier to inspect)
            log.info("Verifying dump", extra={"instance": instance_name, "schema": schema_name})
            self.verify(raw_path)

            # 3. Compress
            log.info("Compressing dump", extra={"instance": instance_name, "schema": schema_name})
            with raw_path.open("rb") as f_in, gzip.open(gz_path, "wb") as f_out:
                shutil.copyfileobj(f_in, f_out)

            # 4. Optional local copy (if BACKUP_LOCAL_PATH env var is set)
            local_path_env = os.environ.get("BACKUP_LOCAL_PATH")
            if local_path_env:
                dest = Path(local_path_env) / instance_name / schema_name / self._filename()
                dest.parent.mkdir(parents=True, exist_ok=True)
                log.info("Copying to local path", extra={"path": str(dest)})
                shutil.copy2(gz_path, dest)

            # 5. S3 Upload & Retention
            self.storage.upload(gz_path, instance_name, schema_name)
            self.storage.apply_retention(instance_name, schema_name, self.schema.keep)

        log.info("Backup complete", extra={"instance": instance_name, "schema": schema_name})
