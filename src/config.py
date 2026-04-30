"""YAML config loader with environment variable substitution and validation."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

_ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")


def _substitute_env(value: str) -> str:
    """Replace ${VAR} patterns with their environment variable values."""
    def replace(match: re.Match) -> str:
        var_name = match.group(1)
        val = os.environ.get(var_name)
        if val is None:
            raise ValueError(
                f"Environment variable '{var_name}' referenced in config is not set."
            )
        return val

    return _ENV_VAR_RE.sub(replace, value)


def _resolve_strings(obj):
    """Recursively resolve env vars in all string values of a dict/list."""
    if isinstance(obj, str):
        return _substitute_env(obj)
    if isinstance(obj, dict):
        return {k: _resolve_strings(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_strings(item) for item in obj]
    return obj


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class SchemaConfig:
    name: str
    cron: str
    keep: int


@dataclass
class InstanceConfig:
    name: str
    type: str           # "postgresql" | "mysql"
    host: str
    port: int
    user: str
    password: str
    schemas: list[SchemaConfig]


@dataclass
class S3Config:
    bucket: str
    region: str
    prefix: str = ""
    endpoint_url: Optional[str] = None


@dataclass
class AppConfig:
    s3: S3Config
    instances: list[InstanceConfig]


# ── Loader ────────────────────────────────────────────────────────────────────

def load_config(path: str | Path) -> AppConfig:
    with open(path) as f:
        raw = yaml.safe_load(f)

    raw = _resolve_strings(raw)

    # Defaults
    global_keep: int = raw.get("defaults", {}).get("keep", 7)

    # S3
    s3_raw = raw.get("s3", {})
    s3 = S3Config(
        bucket=s3_raw["bucket"],
        region=s3_raw.get("region", os.environ.get("AWS_DEFAULT_REGION", "us-east-1")),
        prefix=s3_raw.get("prefix", ""),
        endpoint_url=s3_raw.get("endpoint_url", os.environ.get("AWS_ENDPOINT_URL")),
    )

    # Instances
    instances: list[InstanceConfig] = []
    for inst_raw in raw.get("instances", []):
        db_type = inst_raw["type"].lower()
        if db_type not in ("postgresql", "mysql"):
            raise ValueError(
                f"Instance '{inst_raw['name']}': unsupported type '{db_type}'. "
                "Must be 'postgresql' or 'mysql'."
            )

        instance_cron: str = inst_raw.get("cron")
        if not instance_cron:
            raise ValueError(
                f"Instance '{inst_raw['name']}' has no 'cron' configured."
            )
        instance_keep: int = inst_raw.get("keep", global_keep)

        schemas: list[SchemaConfig] = []
        for schema_raw in inst_raw.get("schemas", []):
            schemas.append(SchemaConfig(
                name=schema_raw["name"],
                cron=schema_raw.get("cron", instance_cron),
                keep=schema_raw.get("keep", instance_keep),
            ))

        if not schemas:
            raise ValueError(
                f"Instance '{inst_raw['name']}' has no schemas configured."
            )

        instances.append(InstanceConfig(
            name=inst_raw["name"],
            type=db_type,
            host=inst_raw["host"],
            port=int(inst_raw.get("port", 5432 if db_type == "postgresql" else 3306)),
            user=inst_raw["user"],
            password=inst_raw["password"],
            schemas=schemas,
        ))

    return AppConfig(s3=s3, instances=instances)
