"""APScheduler setup: register one cron job per schema, isolated error handling."""

from __future__ import annotations

from typing import Optional

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.backup.base import BackupJob
from src.backup.mysql import MySQLBackupJob
from src.backup.postgresql import PostgreSQLBackupJob
from src.config import AppConfig, InstanceConfig, SchemaConfig
from src.logger import get_logger
from src.storage.s3 import S3Storage

log = get_logger(__name__)


def _make_job(instance: InstanceConfig, schema: SchemaConfig, storage: S3Storage) -> BackupJob:
    if instance.type == "postgresql":
        return PostgreSQLBackupJob(instance, schema, storage)
    return MySQLBackupJob(instance, schema, storage)


def _run_job(instance: InstanceConfig, schema: SchemaConfig, storage: S3Storage) -> None:
    """Wrapper that catches all exceptions so a failing job never kills the scheduler."""
    try:
        job = _make_job(instance, schema, storage)
        job.run()
    except Exception:
        log.error(
            "Backup job failed — skipping",
            exc_info=True,
            extra={"instance": instance.name, "schema": schema.name},
        )


def build_scheduler(config: AppConfig) -> BlockingScheduler:
    storage = S3Storage(
        bucket=config.s3.bucket,
        region=config.s3.region,
        prefix=config.s3.prefix,
        endpoint_url=config.s3.endpoint_url,
    )

    scheduler = BlockingScheduler(timezone="UTC")

    for instance in config.instances:
        for schema in instance.schemas:
            job_id = f"{instance.name}__{schema.name}"
            try:
                trigger = CronTrigger.from_crontab(schema.cron, timezone="UTC")
            except Exception as exc:
                log.error(
                    "Invalid cron expression — job skipped",
                    extra={"instance": instance.name, "schema": schema.name, "cron": schema.cron, "error": str(exc)},
                )
                continue

            scheduler.add_job(
                _run_job,
                trigger=trigger,
                id=job_id,
                args=[instance, schema, storage],
                max_instances=1,          # Prevent overlap if a job runs long
                coalesce=True,            # Skip missed runs instead of piling up
                replace_existing=True,
            )
            log.info(
                "Registered backup job",
                extra={
                    "job_id": job_id,
                    "instance": instance.name,
                    "schema": schema.name,
                    "cron": schema.cron,
                    "keep": schema.keep,
                },
            )

    return scheduler
