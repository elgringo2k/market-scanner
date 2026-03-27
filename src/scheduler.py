"""Scheduler component — triggers scrape runs on a configurable interval."""
from __future__ import annotations

import asyncio
import os
import threading
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.logger import get_logger
from src.runner import run

logger = get_logger(__name__)

_run_lock = threading.Event()


def _trigger_run() -> None:
    """Called by APScheduler on each interval tick."""
    if _run_lock.is_set():
        logger.warning("Run already in progress; skipping scheduled trigger")
        return

    _run_lock.set()
    start_time = datetime.now(timezone.utc)
    logger.info("Scheduled run starting", extra={"start_time": start_time.isoformat()})

    try:
        asyncio.run(run())
    except SystemExit:
        # runner calls sys.exit on fatal errors; treat as a completed (failed) run
        pass
    except Exception as exc:
        logger.error("Unhandled error during scheduled run", extra={"error": str(exc)})
    finally:
        end_time = datetime.now(timezone.utc)
        logger.info("Scheduled run finished", extra={"end_time": end_time.isoformat()})
        _run_lock.clear()


def start() -> None:
    """Start the blocking scheduler. Does not return until the process is stopped."""
    interval_minutes = int(os.environ.get("POLL_INTERVAL_MINUTES", "10"))
    logger.info("Scheduler starting", extra={"poll_interval_minutes": interval_minutes})

    scheduler = BlockingScheduler()
    scheduler.add_job(
        _trigger_run,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="scrape_run",
        max_instances=1,
        next_run_time=datetime.now(timezone.utc),  # run immediately on startup
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")
