"""Tests for config loading: env substitution, inheritance, validation."""

import os
import textwrap

import pytest

from src.config import load_config


@pytest.fixture
def config_file(tmp_path):
    def _write(content: str):
        p = tmp_path / "config.yaml"
        p.write_text(textwrap.dedent(content))
        return p
    return _write


def test_env_substitution(config_file, monkeypatch):
    monkeypatch.setenv("PG_PASS", "secret123")
    p = config_file("""
        s3:
          bucket: my-bucket
          region: us-east-1
        defaults:
          keep: 5
        instances:
          - name: pg1
            type: postgresql
            host: localhost
            port: 5432
            user: admin
            password: "${PG_PASS}"
            cron: "0 1 * * *"
            schemas:
              - name: mydb
    """)
    cfg = load_config(p)
    assert cfg.instances[0].password == "secret123"


def test_schema_inherits_instance_cron_and_keep(config_file, monkeypatch):
    monkeypatch.setenv("PG_PASS", "x")
    p = config_file("""
        s3:
          bucket: b
          region: us-east-1
        defaults:
          keep: 3
        instances:
          - name: pg1
            type: postgresql
            host: h
            port: 5432
            user: u
            password: "${PG_PASS}"
            cron: "0 2 * * *"
            keep: 10
            schemas:
              - name: db1
              - name: db2
                cron: "0 4 * * *"
                keep: 2
    """)
    cfg = load_config(p)
    schemas = {s.name: s for s in cfg.instances[0].schemas}
    # db1 inherits from instance
    assert schemas["db1"].cron == "0 2 * * *"
    assert schemas["db1"].keep == 10
    # db2 has overrides
    assert schemas["db2"].cron == "0 4 * * *"
    assert schemas["db2"].keep == 2


def test_instance_inherits_global_keep(config_file, monkeypatch):
    monkeypatch.setenv("PG_PASS", "x")
    p = config_file("""
        s3:
          bucket: b
          region: us-east-1
        defaults:
          keep: 7
        instances:
          - name: pg1
            type: postgresql
            host: h
            port: 5432
            user: u
            password: "${PG_PASS}"
            cron: "0 2 * * *"
            schemas:
              - name: db1
    """)
    cfg = load_config(p)
    assert cfg.instances[0].schemas[0].keep == 7


def test_invalid_db_type_raises(config_file, monkeypatch):
    monkeypatch.setenv("PG_PASS", "x")
    p = config_file("""
        s3:
          bucket: b
          region: us-east-1
        instances:
          - name: bad
            type: oracle
            host: h
            port: 1521
            user: u
            password: "${PG_PASS}"
            cron: "0 2 * * *"
            schemas:
              - name: db1
    """)
    with pytest.raises(ValueError, match="unsupported type"):
        load_config(p)


def test_missing_env_var_raises(config_file):
    p = config_file("""
        s3:
          bucket: b
          region: us-east-1
        instances:
          - name: pg1
            type: postgresql
            host: h
            port: 5432
            user: u
            password: "${DOES_NOT_EXIST}"
            cron: "0 2 * * *"
            schemas:
              - name: db1
    """)
    with pytest.raises(ValueError, match="DOES_NOT_EXIST"):
        load_config(p)
