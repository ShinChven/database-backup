"""S3 storage operations: upload, list, and retention-based deletion."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from src.logger import get_logger

log = get_logger(__name__)


class S3Storage:
    def __init__(
        self,
        bucket: str,
        region: str,
        prefix: str = "",
        endpoint_url: Optional[str] = None,
    ):
        self.bucket = bucket
        self.prefix = prefix.rstrip("/")
        session = boto3.session.Session()
        self.client = session.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url or os.environ.get("AWS_ENDPOINT_URL"),
        )

    def _schema_prefix(self, instance_name: str, schema_name: str) -> str:
        parts = [self.prefix, instance_name, schema_name] if self.prefix else [instance_name, schema_name]
        return "/".join(parts) + "/"

    def upload(self, local_path: Path, instance_name: str, schema_name: str) -> str:
        """Upload a file and return its S3 key."""
        key = self._schema_prefix(instance_name, schema_name) + local_path.name
        log.info(
            "Uploading backup",
            extra={"instance": instance_name, "schema": schema_name, "s3_key": key},
        )
        try:
            self.client.upload_file(str(local_path), self.bucket, key)
        except (BotoCoreError, ClientError) as exc:
            raise RuntimeError(f"S3 upload failed for {key}: {exc}") from exc
        log.info(
            "Upload complete",
            extra={"instance": instance_name, "schema": schema_name, "s3_key": key},
        )
        return key

    def apply_retention(self, instance_name: str, schema_name: str, keep: int) -> None:
        """Delete oldest backup files, keeping only `keep` most recent ones."""
        prefix = self._schema_prefix(instance_name, schema_name)
        paginator = self.client.get_paginator("list_objects_v2")
        keys: list[tuple[str, str]] = []  # (last_modified_isoformat, key)

        try:
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    keys.append((obj["LastModified"].isoformat(), obj["Key"]))
        except (BotoCoreError, ClientError) as exc:
            raise RuntimeError(f"S3 list failed for prefix {prefix}: {exc}") from exc

        # Sort newest-first
        keys.sort(key=lambda x: x[0], reverse=True)
        to_delete = keys[keep:]

        if not to_delete:
            log.info(
                "Retention: nothing to delete",
                extra={"instance": instance_name, "schema": schema_name, "keep": keep, "total": len(keys)},
            )
            return

        delete_objects = [{"Key": k} for _, k in to_delete]
        try:
            self.client.delete_objects(
                Bucket=self.bucket,
                Delete={"Objects": delete_objects},
            )
        except (BotoCoreError, ClientError) as exc:
            raise RuntimeError(f"S3 delete failed: {exc}") from exc

        log.info(
            "Retention applied",
            extra={
                "instance": instance_name,
                "schema": schema_name,
                "keep": keep,
                "deleted": len(to_delete),
            },
        )
