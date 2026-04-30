"""Tests for S3Storage: upload, list, and retention using moto."""

import gzip
from pathlib import Path
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws

from src.storage.s3 import S3Storage


BUCKET = "test-bucket"
REGION = "us-east-1"


@pytest.fixture
def s3_storage():
    with mock_aws():
        # Create bucket
        boto3.client("s3", region_name=REGION).create_bucket(Bucket=BUCKET)
        yield S3Storage(bucket=BUCKET, region=REGION, prefix="backups")


def _put_object(bucket: str, key: str, region: str = REGION) -> None:
    boto3.client("s3", region_name=region).put_object(
        Bucket=bucket, Key=key, Body=b"data"
    )


def test_upload(s3_storage, tmp_path):
    with mock_aws():
        boto3.client("s3", region_name=REGION).create_bucket(Bucket=BUCKET)
        storage = S3Storage(bucket=BUCKET, region=REGION, prefix="backups")
        f = tmp_path / "mydb_20240101_020000.sql.gz"
        f.write_bytes(gzip.compress(b"SELECT 1;"))
        key = storage.upload(f, "prod-pg", "mydb")
        assert key == "backups/prod-pg/mydb/mydb_20240101_020000.sql.gz"


def test_apply_retention_deletes_oldest(tmp_path):
    with mock_aws():
        client = boto3.client("s3", region_name=REGION)
        client.create_bucket(Bucket=BUCKET)
        storage = S3Storage(bucket=BUCKET, region=REGION, prefix="backups")

        # Put 5 objects
        for i in range(1, 6):
            key = f"backups/prod-pg/mydb/mydb_2024010{i}_020000.sql.gz"
            client.put_object(Bucket=BUCKET, Key=key, Body=b"data")

        storage.apply_retention("prod-pg", "mydb", keep=3)

        remaining = client.list_objects_v2(
            Bucket=BUCKET, Prefix="backups/prod-pg/mydb/"
        ).get("Contents", [])
        assert len(remaining) == 3


def test_apply_retention_nothing_to_delete():
    with mock_aws():
        client = boto3.client("s3", region_name=REGION)
        client.create_bucket(Bucket=BUCKET)
        storage = S3Storage(bucket=BUCKET, region=REGION, prefix="backups")

        for i in range(1, 4):
            key = f"backups/prod-pg/mydb/mydb_2024010{i}_020000.sql.gz"
            client.put_object(Bucket=BUCKET, Key=key, Body=b"data")

        # keep=5, only 3 exist — nothing should be deleted
        storage.apply_retention("prod-pg", "mydb", keep=5)

        remaining = client.list_objects_v2(
            Bucket=BUCKET, Prefix="backups/prod-pg/mydb/"
        ).get("Contents", [])
        assert len(remaining) == 3
