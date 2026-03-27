"""Runner component — orchestrates a single end-to-end scrape run."""
from __future__ import annotations

import sys
import time

from src.logger import get_logger
from src.models import OddsRecord
from src.parser import parse_listing_page
from src.scraper import Scraper, ScraperError
from src.supabase_client import SupabaseClient

logger = get_logger(__name__)


def _odds_changed(record: OddsRecord, latest: dict | None) -> bool:
    """Return True if odds differ from the latest stored row (or no row exists)."""
    if latest is None:
        return True
    return (
        float(latest["best_home_odds"]) != record.best_home_odds
        or float(latest["best_draw_odds"]) != record.best_draw_odds
        or float(latest["best_away_odds"]) != record.best_away_odds
    )


async def run() -> None:
    """Execute one full scrape run: discover matches, fetch odds, persist to Supabase."""
    start_time = time.monotonic()
    logger.info("Run started")

    async with Scraper() as scraper:
        # --- Step 1: fetch and parse the listing page (odds included) ---
        try:
            listing_html = await scraper.fetch_listing_page()
        except ScraperError as exc:
            logger.error("Listing page fetch failed", extra={"error": str(exc)})
            sys.exit(1)

        matches, records = parse_listing_page(listing_html)

        if not matches:
            logger.warning("No matches found on listing page; aborting run")
            sys.exit(1)

        logger.info("Matches discovered", extra={"count": len(matches)})
        discarded = len(matches) - len(records)

    # --- Step 2: persist only changed odds to Supabase ---
    if records:
        client = SupabaseClient()
        latest = client.get_latest_odds([str(r.match_id) for r in records])

        changed = [
            r for r in records
            if _odds_changed(r, latest.get(str(r.match_id)))
        ]

        skipped = len(records) - len(changed)
        if skipped:
            logger.info("Skipping unchanged odds", extra={"count": skipped})

        client.insert_odds_records(changed)

    duration = time.monotonic() - start_time
    logger.info(
        "Run completed",
        extra={
            "total_matches": len(matches),
            "records_inserted": len(changed) if records else 0,
            "records_discarded": discarded,
            "duration_seconds": round(duration, 2),
        },
    )
