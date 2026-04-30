"""Tests for MySQLBackupJob: dump and verify logic."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.backup.mysql import MySQLBackupJob, _MIN_DUMP_BYTES, _TRAILER_MARKER
from src.config import InstanceConfig, SchemaConfig


@pytest.fixture
def instance():
    return InstanceConfig(
        name="test-mysql",
        type="mysql",
        host="localhost",
        port=3306,
        user="admin",
        password="secret",
        schemas=[],
    )


@pytest.fixture
def schema():
    return SchemaConfig(name="users_db", cron="0 2 * * *", keep=7)


@pytest.fixture
def job(instance, schema):
    return MySQLBackupJob(instance, schema, storage=MagicMock())


def test_dump_success(job, tmp_path):
    dest = tmp_path / "users_db.sql"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        job.dump(dest)
        cmd = mock_run.call_args[0][0]
        assert "mysqldump" in cmd
        assert "users_db" in cmd


def test_dump_failure_raises(job, tmp_path):
    dest = tmp_path / "users_db.sql"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="access denied")
        with pytest.raises(RuntimeError, match="mysqldump failed"):
            job.dump(dest)


def test_verify_missing_file_raises(job, tmp_path):
    with pytest.raises(RuntimeError, match="missing"):
        job.verify(tmp_path / "nonexistent.sql")


def test_verify_too_small_raises(job, tmp_path):
    small = tmp_path / "small.sql"
    small.write_bytes(b"x" * 10)
    with pytest.raises(RuntimeError, match="too small"):
        job.verify(small)


def test_verify_missing_trailer_raises(job, tmp_path):
    dump = tmp_path / "users_db.sql"
    dump.write_bytes(b"CREATE TABLE foo ... " * 100)  # No trailer
    with pytest.raises(RuntimeError, match="trailer"):
        job.verify(dump)


def test_verify_success(job, tmp_path):
    dump = tmp_path / "users_db.sql"
    content = b"CREATE TABLE foo;\n" * 100 + f"\n{_TRAILER_MARKER} on 2024-01-01\n".encode()
    dump.write_bytes(content)
    job.verify(dump)  # Should not raise
