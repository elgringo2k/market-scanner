"""Tests for src/parser.py

# Feature: oddschecker-scraper
# Property 1: Parser extracts all required Match fields
# Property 2: Best odds equal the maximum across bookmakers
# Property 3: Parser extracts all required OddsRecord fields
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.models import Match
from src.parser import parse_listing_page, parse_odds_page


# ---------------------------------------------------------------------------
# HTML generation helpers
# ---------------------------------------------------------------------------

def _make_listing_html(fixtures: list[tuple[str, str, str, str]]) -> str:
    """Build a minimal listing-page HTML with one <tr> per fixture.

    Each fixture is (home_team, away_team, kickoff_str, odds_path).
    """
    rows = ""
    for home, away, kickoff, path in fixtures:
        rows += (
            f'<tr class="coupon-row" data-event-name="{home} v {away}">'
            f'<td class="date-time" data-start-time="{kickoff}">{kickoff}</td>'
            f'<td><a href="{path}">odds</a></td>'
            f"</tr>\n"
        )
    return f"<html><body><table>{rows}</table></body></html>"


def _make_odds_html(bookmaker_rows: list[tuple[float, float, float]]) -> str:
    """Build a minimal odds-page HTML with one <tr> per bookmaker."""
    rows = ""
    for h, d, a in bookmaker_rows:
        rows += (
            f'<tr class="diff-row" data-bk="bk1">'
            f'<td class="odds">{h}</td>'
            f'<td class="odds">{d}</td>'
            f'<td class="odds">{a}</td>'
            f"</tr>\n"
        )
    return f"<html><body><table><tbody>{rows}</tbody></table></body></html>"


def _make_match(**overrides) -> Match:
    defaults = dict(
        match_id=uuid4(),
        home_team="Arsenal",
        away_team="Chelsea",
        starts_at=datetime(2024, 8, 17, 15, 0, tzinfo=timezone.utc),
        odds_page_url="https://www.oddschecker.com/football/english/premier-league/arsenal-v-chelsea/winner",
    )
    defaults.update(overrides)
    return Match(**defaults)


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Safe team names: printable ASCII, no " v " substring, non-empty
_safe_text = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters=" "),
    min_size=2,
    max_size=30,
).filter(lambda s: s.strip() and " v " not in s)

_valid_odds_value = st.floats(min_value=1.01, max_value=100.0, allow_nan=False, allow_infinity=False)

_bookmaker_row = st.tuples(_valid_odds_value, _valid_odds_value, _valid_odds_value)

_odds_page_path = st.just("/football/english/premier-league/team-a-v-team-b/winner")


# ---------------------------------------------------------------------------
# Property 1: Parser extracts all required Match fields
# Feature: oddschecker-scraper, Property 1: Parser extracts all required Match fields
# Validates: Requirements 1.2
# ---------------------------------------------------------------------------

@given(
    home=_safe_text,
    away=_safe_text,
    path=_odds_page_path,
)
@settings(max_examples=100)
def test_parse_listing_page_extracts_all_match_fields(home: str, away: str, path: str) -> None:
    """Every Match returned by parse_listing_page has all required non-empty fields.

    # Feature: oddschecker-scraper, Property 1: Parser extracts all required Match fields
    # Validates: Requirements 1.2
    """
    html = _make_listing_html([(home.strip(), away.strip(), "17 Aug 2024 15:00", path)])
    matches = parse_listing_page(html)

    assert len(matches) >= 1, "Expected at least one match to be parsed"
    for match in matches:
        assert match.home_team, "home_team must be non-empty"
        assert match.away_team, "away_team must be non-empty"
        assert match.starts_at is not None, "starts_at must not be None"
        assert isinstance(match.starts_at, datetime), "starts_at must be a datetime"
        assert match.odds_page_url, "odds_page_url must be non-empty"
        assert isinstance(match.match_id, UUID), "match_id must be a UUID"


# ---------------------------------------------------------------------------
# Property 2: Best odds equal the maximum across bookmakers
# Feature: oddschecker-scraper, Property 2: Best odds equal the maximum across bookmakers
# Validates: Requirements 2.3
# ---------------------------------------------------------------------------

@given(rows=st.lists(_bookmaker_row, min_size=1, max_size=20))
@settings(max_examples=100)
def test_best_odds_equal_max_across_bookmakers(rows: list[tuple[float, float, float]]) -> None:
    """best_home/draw/away_odds must each equal max() of the corresponding column.

    # Feature: oddschecker-scraper, Property 2: Best odds equal the maximum across bookmakers
    # Validates: Requirements 2.3
    """
    html = _make_odds_html(rows)
    match = _make_match()
    record = parse_odds_page(html, match)

    assert record is not None, "Expected a valid OddsRecord"

    expected_home = max(r[0] for r in rows)
    expected_draw = max(r[1] for r in rows)
    expected_away = max(r[2] for r in rows)

    assert abs(record.best_home_odds - expected_home) < 1e-9
    assert abs(record.best_draw_odds - expected_draw) < 1e-9
    assert abs(record.best_away_odds - expected_away) < 1e-9


# ---------------------------------------------------------------------------
# Property 3: Parser extracts all required OddsRecord fields
# Feature: oddschecker-scraper, Property 3: Parser extracts all required OddsRecord fields
# Validates: Requirements 3.1
# ---------------------------------------------------------------------------

@given(rows=st.lists(_bookmaker_row, min_size=1, max_size=10))
@settings(max_examples=100)
def test_parse_odds_page_extracts_all_required_fields(rows: list[tuple[float, float, float]]) -> None:
    """OddsRecord returned by parse_odds_page has non-None values for all required fields.

    # Feature: oddschecker-scraper, Property 3: Parser extracts all required OddsRecord fields
    # Validates: Requirements 3.1
    """
    html = _make_odds_html(rows)
    match = _make_match()
    record = parse_odds_page(html, match)

    assert record is not None
    assert record.match_id is not None
    assert record.home_team
    assert record.away_team
    assert record.starts_at is not None
    assert record.market
    assert record.best_home_odds is not None
    assert record.best_draw_odds is not None
    assert record.best_away_odds is not None
    assert record.fetched_at is not None


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_parse_listing_page_returns_empty_for_blank_html() -> None:
    assert parse_listing_page("<html><body></body></html>") == []


def test_parse_listing_page_multiple_fixtures() -> None:
    fixtures = [
        ("Arsenal", "Chelsea", "17 Aug 2024 15:00", "/football/arsenal-v-chelsea/winner"),
        ("Liverpool", "Man City", "18 Aug 2024 16:30", "/football/liverpool-v-man-city/winner"),
    ]
    html = _make_listing_html(fixtures)
    matches = parse_listing_page(html)
    assert len(matches) == 2
    teams = {(m.home_team, m.away_team) for m in matches}
    assert ("Arsenal", "Chelsea") in teams
    assert ("Liverpool", "Man City") in teams


def test_parse_listing_page_generates_unique_match_ids() -> None:
    fixtures = [
        ("Arsenal", "Chelsea", "17 Aug 2024 15:00", "/football/arsenal-v-chelsea/winner"),
        ("Liverpool", "Man City", "18 Aug 2024 16:30", "/football/liverpool-v-man-city/winner"),
    ]
    html = _make_listing_html(fixtures)
    matches = parse_listing_page(html)
    ids = [m.match_id for m in matches]
    assert len(ids) == len(set(ids)), "Each match must have a unique match_id"


def test_parse_odds_page_returns_none_for_empty_html() -> None:
    match = _make_match()
    result = parse_odds_page("<html><body></body></html>", match)
    assert result is None


def test_parse_odds_page_skips_rows_with_odds_at_or_below_one() -> None:
    # All rows have invalid odds (≤ 1.0) — should return None
    html = _make_odds_html([(1.0, 0.9, 1.0)])
    match = _make_match()
    result = parse_odds_page(html, match)
    assert result is None


def test_parse_odds_page_uses_match_metadata() -> None:
    match = _make_match(home_team="Spurs", away_team="West Ham")
    html = _make_odds_html([(2.5, 3.1, 2.8)])
    record = parse_odds_page(html, match)
    assert record is not None
    assert record.home_team == "Spurs"
    assert record.away_team == "West Ham"
    assert record.match_id == match.match_id
    assert record.market == "Match Result"


def test_parse_odds_page_fetched_at_is_utc() -> None:
    html = _make_odds_html([(2.0, 3.0, 4.0)])
    match = _make_match()
    record = parse_odds_page(html, match)
    assert record is not None
    assert record.fetched_at.tzinfo is not None
