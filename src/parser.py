"""Parser component — transforms rendered HTML into Match and OddsRecord objects.

OddsChecker is a React/Next.js app. Match data is embedded as JSON in HTML
comments (<!-- {...} -->) rather than in the DOM. We extract from those blobs.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid5, NAMESPACE_URL

from bs4 import BeautifulSoup

from src.logger import get_logger
from src.models import Match, OddsRecord

logger = get_logger(__name__)

_BASE_URL = "https://www.oddschecker.com"


def _parse_iso(raw: str) -> datetime:
    """Parse an ISO-8601 UTC string into a UTC-aware datetime."""
    raw = raw.rstrip("Z")
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return datetime.now(timezone.utc)


def _extract_json_blobs(html: str) -> list[dict]:
    """Return all JSON objects embedded as HTML comments."""
    blobs = []
    for raw in re.findall(r"<!--(\{.*?\})-->", html, re.DOTALL):
        try:
            blobs.append(json.loads(raw))
        except json.JSONDecodeError:
            pass
    return blobs


def _build_best_odds(blob: dict) -> dict[int, dict[str, float]]:
    """Return {subeventId: {HOME, DRAW, AWAY}} best decimal odds from a blob."""
    markets = blob.get("markets", {}).get("entities", {})
    bets = blob.get("bets", {}).get("entities", {})
    best_odds = blob.get("bestOdds", {}).get("entities", {})

    # marketId (str) -> subeventId, only 1x2 markets (marketTemplateId == 1)
    market_to_sub: dict[str, int] = {
        str(m["ocMarketId"]): m["subeventId"]
        for m in markets.values()
        if m.get("marketTemplateId") == 1
    }

    # subeventId -> {HOME/DRAW/AWAY -> best decimal seen}
    sub_odds: dict[int, dict[str, float]] = {}
    for bet_id, bet in bets.items():
        role = bet.get("genericName")
        if role not in ("HOME", "DRAW", "AWAY"):
            continue
        odds = best_odds.get(bet_id)
        if not odds:
            continue
        sub_id = market_to_sub.get(str(bet["marketId"]))
        if sub_id is None:
            continue
        decimal = odds.get("decimal", 0.0)
        current = sub_odds.setdefault(sub_id, {})
        if decimal > current.get(role, 0.0):
            current[role] = decimal

    return sub_odds


def parse_listing_page(html: str) -> tuple[list[Match], list[OddsRecord]]:
    """Extract Matches and OddsRecords directly from the listing page HTML.

    OddsChecker embeds all 1x2 best-odds data in JSON comment blobs, so there
    is no need to visit individual match pages.
    """
    matches_by_id: dict[UUID, Match] = {}
    records_by_id: dict[UUID, OddsRecord] = {}
    fetched_at = datetime.now(timezone.utc)

    for blob in _extract_json_blobs(html):
        subevents = blob.get("subevents", {})
        if not subevents.get("ids"):
            continue

        best_odds_map = _build_best_odds(blob)

        for se in subevents["entities"].values():
            try:
                home_team = se.get("homeTeamName", "").strip()
                away_team = se.get("awayTeamName", "").strip()
                url_map = se.get("urlMap", "")
                start_time = se.get("startTime", "")
                sub_id = se.get("id")

                if not home_team or not away_team or not url_map:
                    continue

                odds_page_url = f"{_BASE_URL}/football/english/premier-league/{url_map}/winner"
                starts_at = _parse_iso(start_time) if start_time else datetime.now(timezone.utc)
                match_key = f"oddschecker:{home_team}:{away_team}:{starts_at.isoformat()}"
                match_id = uuid5(NAMESPACE_URL, match_key)

                if match_id not in matches_by_id:
                    matches_by_id[match_id] = Match(
                        match_id=match_id,
                        home_team=home_team,
                        away_team=away_team,
                        starts_at=starts_at,
                        odds_page_url=odds_page_url,
                    )

                odds = best_odds_map.get(sub_id, {})
                home_dec = odds.get("HOME", 0.0)
                draw_dec = odds.get("DRAW", 0.0)
                away_dec = odds.get("AWAY", 0.0)

                if home_dec > 1.0 and draw_dec > 1.0 and away_dec > 1.0:
                    existing = records_by_id.get(match_id)
                    if existing:
                        home_dec = max(home_dec, existing.best_home_odds)
                        draw_dec = max(draw_dec, existing.best_draw_odds)
                        away_dec = max(away_dec, existing.best_away_odds)
                    try:
                        record = OddsRecord(
                            match_id=match_id,
                            home_team=home_team,
                            away_team=away_team,
                            starts_at=starts_at,
                            market="Match Result",
                            best_home_odds=home_dec,
                            best_draw_odds=draw_dec,
                            best_away_odds=away_dec,
                            fetched_at=fetched_at,
                        )
                        OddsRecord.from_dict(record.to_dict())
                        records_by_id[match_id] = record
                        logger.info(
                            "Odds parsed",
                            extra={
                                "match_id": str(match_id),
                                "home_team": home_team,
                                "away_team": away_team,
                                "best_home_odds": home_dec,
                                "best_draw_odds": draw_dec,
                                "best_away_odds": away_dec,
                            },
                        )
                    except ValueError as exc:
                        logger.warning("OddsRecord validation failed", extra={"error": str(exc)})
                else:
                    logger.warning(
                        "Missing or invalid odds for match",
                        extra={"home_team": home_team, "away_team": away_team, "odds": odds},
                    )

            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to parse subevent", extra={"error": str(exc)})

        if matches_by_id:
            break  # found the right blob

    matches = list(matches_by_id.values())
    records = list(records_by_id.values())
    logger.info("Listing page parsed", extra={"matches_found": len(matches), "records_found": len(records)})
    return matches, records


# ---------------------------------------------------------------------------
# Odds page parser
# ---------------------------------------------------------------------------

def parse_odds_page(html: str, match: Match) -> Optional[OddsRecord]:
    """Extract and validate an OddsRecord from a /winner odds page.

    Returns None (and logs) on any validation failure.
    """
    soup = BeautifulSoup(html, "lxml")
    fetched_at = datetime.now(timezone.utc)

    home_odds_list: list[float] = []
    draw_odds_list: list[float] = []
    away_odds_list: list[float] = []

    # OddsChecker odds tables: each bookmaker row has three <td> cells with
    # decimal odds.  The header row identifies the column order (1 / X / 2).
    # We look for the most common table/row selectors.
    rows = soup.select(
        "tr.diff-row, tr[data-bk], tr.bk-odds-row, "
        "tbody tr"
    )

    for row in rows:
        cells = row.select("td.odds, td[data-odig], td.bc")
        if len(cells) < 3:
            # Try generic td children that look like decimal odds
            cells = [
                td for td in row.find_all("td")
                if re.match(r"^\d+\.\d+$", td.get_text(strip=True))
            ]
        if len(cells) < 3:
            continue

        try:
            h = float(cells[0].get_text(strip=True))
            d = float(cells[1].get_text(strip=True))
            a = float(cells[2].get_text(strip=True))
        except (ValueError, IndexError):
            continue

        # Only keep rows where all three values are valid odds (> 1.0)
        if h > 1.0 and d > 1.0 and a > 1.0:
            home_odds_list.append(h)
            draw_odds_list.append(d)
            away_odds_list.append(a)

    if not home_odds_list:
        logger.warning(
            "No bookmaker odds found on odds page",
            extra={"match_id": str(match.match_id), "url": match.odds_page_url},
        )
        return None

    best_home = max(home_odds_list)
    best_draw = max(draw_odds_list)
    best_away = max(away_odds_list)

    try:
        record = OddsRecord(
            match_id=match.match_id,
            home_team=match.home_team,
            away_team=match.away_team,
            starts_at=match.starts_at,
            market="Match Result",
            best_home_odds=best_home,
            best_draw_odds=best_draw,
            best_away_odds=best_away,
            fetched_at=fetched_at,
        )
        # Validate via round-trip through from_dict
        OddsRecord.from_dict(record.to_dict())
    except ValueError as exc:
        logger.warning(
            "OddsRecord validation failed",
            extra={"match_id": str(match.match_id), "error": str(exc)},
        )
        return None

    logger.info(
        "Odds parsed",
        extra={
            "match_id": str(match.match_id),
            "home_team": match.home_team,
            "away_team": match.away_team,
            "best_home_odds": best_home,
            "best_draw_odds": best_draw,
            "best_away_odds": best_away,
        },
    )
    return record
