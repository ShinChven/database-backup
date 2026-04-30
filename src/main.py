"""Entrypoint: load config, build scheduler, run."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

from src.config import load_config
from src.logger import get_logger
from src.scheduler import build_scheduler

CONFIG_PATH = Path("/app/config.yaml")

log = get_logger(__name__)


def main() -> None:
    # Load .env if present (dev convenience — not needed in production)
    load_dotenv()

    if not CONFIG_PATH.exists():
        log.error("Config file not found", extra={"path": str(CONFIG_PATH)})
        sys.exit(1)

    log.info("Loading configuration", extra={"path": str(CONFIG_PATH)})
    try:
        config = load_config(CONFIG_PATH)
    except Exception:
        log.error("Failed to load configuration", exc_info=True)
        sys.exit(1)

    log.info(
        "Configuration loaded",
        extra={
            "instances": len(config.instances),
            "total_schemas": sum(len(i.schemas) for i in config.instances),
        },
    )

    scheduler = build_scheduler(config)

    log.info("Starting scheduler")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped")


if __name__ == "__main__":
    main()
