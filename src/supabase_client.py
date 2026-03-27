import os
import time

from supabase import create_client, Client

from src.logger import get_logger
from src.models import OddsRecord

logger = get_logger(__name__)

_RETRY_DELAY_SECONDS = 5


class SupabaseClient:
    def __init__(self) -> None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        self._client: Client = create_client(url, key)

    def get_latest_odds(self, match_ids: list[str]) -> dict[str, dict]:
        """Return the most recent odds row per match_id as {match_id: row}."""
        if not match_ids:
            return {}
        try:
            rows = (
                self._client.table("odds_records")
                .select("match_id, best_home_odds, best_draw_odds, best_away_odds")
                .in_("match_id", match_ids)
                .order("fetched_at", desc=True)
                .execute()
                .data
            )
            # Keep only the first (latest) row per match_id
            seen: dict[str, dict] = {}
            for row in rows:
                mid = row["match_id"]
                if mid not in seen:
                    seen[mid] = row
            return seen
        except Exception as exc:
            logger.warning("Failed to fetch latest odds; will insert all", extra={"error": str(exc)})
            return {}

    def insert_odds_records(self, records: list[OddsRecord]) -> None:
        """Batch insert all records; retries once on failure; raises on second failure."""
        if not records:
            logger.info("No records to insert")
            return

        payload = [r.to_dict() for r in records]

        try:
            self._client.table("odds_records").insert(payload).execute()
            logger.info("Inserted odds records", extra={"count": len(records)})
        except Exception as exc:
            logger.error("Supabase insert failed, retrying", extra={"error": str(exc)})
            time.sleep(_RETRY_DELAY_SECONDS)
            try:
                self._client.table("odds_records").insert(payload).execute()
                logger.info("Inserted odds records on retry", extra={"count": len(records)})
            except Exception as exc2:
                logger.error("Supabase insert failed on retry", extra={"error": str(exc2)})
                raise
