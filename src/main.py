"""Entrypoint: load config, build scheduler, run."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from src.config import load_config
from src.logger import get_logger
from src.scheduler import build_scheduler, run_all_once

CONFIG_PATH = Path("/app/config.yaml")

log = get_logger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Database Backup Service")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run backup jobs once and exit immediately",
    )
    parser.add_argument(
        "--instance",
        help="Filter by instance name (only with --once)",
    )
    parser.add_argument(
        "--schema",
        help="Filter by schema name (only with --once)",
    )
    args = parser.parse_args()

    # Load .env if present (dev convenience — not needed in production)
    load_dotenv()

    if not CONFIG_PATH.exists():
        # Fallback to local config.yaml for development
        dev_config = Path("config.yaml")
        if dev_config.exists():
            config_file = dev_config
        else:
            log.error("Config file not found", extra={"path": str(CONFIG_PATH)})
            sys.exit(1)
    else:
        config_file = CONFIG_PATH

    log.info("Loading configuration", extra={"path": str(config_file)})
    try:
        config = load_config(config_file)
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

    if args.once:
        log.info("Running jobs once as requested")
        run_all_once(config, instance_filter=args.instance, schema_filter=args.schema)
        log.info("Manual run complete")
    else:
        scheduler = build_scheduler(config)
        log.info("Starting scheduler")
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            log.info("Scheduler stopped")


if __name__ == "__main__":
    main()
