"""Tests for PostgreSQLBackupJob: dump and verify logic."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.backup.postgresql import PostgreSQLBackupJob
from src.config import InstanceConfig, SchemaConfig


@pytest.fixture
def instance():
    return InstanceConfig(
        name="test-pg",
        type="postgresql",
        host="localhost",
        port=5432,
        user="admin",
        password="secret",
        schemas=[],
    )


@pytest.fixture
def schema():
    return SchemaConfig(name="mydb", cron="0 2 * * *", keep=7)


@pytest.fixture
def job(instance, schema):
    return PostgreSQLBackupJob(instance, schema, storage=MagicMock())


def test_dump_success(job, tmp_path):
    dest = tmp_path / "mydb.sql"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        job.dump(dest)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "pg_dump" in cmd
        assert "--dbname" in cmd
        assert "mydb" in cmd


def test_dump_failure_raises(job, tmp_path):
    dest = tmp_path / "mydb.sql"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="connection refused")
        with pytest.raises(RuntimeError, match="pg_dump failed"):
            job.dump(dest)


def test_verify_missing_file_raises(job, tmp_path):
    with pytest.raises(RuntimeError, match="missing or empty"):
        job.verify(tmp_path / "nonexistent.sql")


def test_verify_empty_file_raises(job, tmp_path):
    empty = tmp_path / "empty.sql"
    empty.write_bytes(b"")
    with pytest.raises(RuntimeError, match="missing or empty"):
        job.verify(empty)


def test_verify_success(job, tmp_path):
    dump = tmp_path / "mydb.sql"
    dump.write_bytes(b"PGDMP" + b"\x00" * 100)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        job.verify(dump)   # Should not raise


def test_verify_restore_list_failure_raises(job, tmp_path):
    dump = tmp_path / "mydb.sql"
    dump.write_bytes(b"corrupted" * 100)
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="not a valid archive")
        with pytest.raises(RuntimeError, match="verification failed"):
            job.verify(dump)
