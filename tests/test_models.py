"""Tests for src/models.py — OddsRecord and Match dataclasses."""
import pytest
from datetime import datetime, timezone
from uuid import UUID, uuid4

from hypothesis import given, settings
from hypothesis import strategies as st

from src.models import Match, OddsRecord


# ---------------------------------------------------------------------------
# Helpers / strategies
# ---------------------------------------------------------------------------

def make_odds_record(**overrides) -> OddsRecord:
    defaults = dict(
        match_id=uuid4(),
        home_team="Arsenal",
        away_team="Chelsea",
        starts_at=datetime(2024, 8, 17, 15, 0, 0, tzinfo=timezone.utc),
        market="Match Result",
        best_home_odds=2.5,
        best_draw_odds=3.1,
        best_away_odds=2.8,
        fetched_at=datetime(2024, 8, 17, 14, 0, 0, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    return OddsRecord(**defaults)


# Strategy for valid odds values (> 1.0, finite floats)
valid_odds = st.floats(min_value=1.01, max_value=1000.0, allow_nan=False, allow_infinity=False)

# Strategy for non-empty team names
team_name = st.text(min_size=1, max_size=50).filter(lambda s: s.strip())

# Strategy for UTC-aware datetimes
utc_datetime = st.datetimes(
    min_value=datetime(2020, 1, 1),
    max_value=datetime(2030, 12, 31),
    timezones=st.just(timezone.utc),
)

# Strategy for valid OddsRecord instances
valid_odds_record = st.builds(
    OddsRecord,
    match_id=st.uuids(),
    home_team=team_name,
    away_team=team_name,
    starts_at=utc_datetime,
    market=st.just("Match Result"),
    best_home_odds=valid_odds,
    best_draw_odds=valid_odds,
    best_away_odds=valid_odds,
    fetched_at=utc_datetime,
)


# ---------------------------------------------------------------------------
# Property 5: OddsRecord serialisation round-trip
# Feature: oddschecker-scraper, Property 5: OddsRecord serialisation round-trip
# Validates: Requirements 3.4, 3.5
# ---------------------------------------------------------------------------

@given(record=valid_odds_record)
@settings(max_examples=100)
def test_odds_record_round_trip(record: OddsRecord):
    """For any valid OddsRecord, from_dict(to_dict(record)) == record."""
    # Validates: Requirements 3.4, 3.5
    result = OddsRecord.from_dict(record.to_dict())
    assert result == record


# ---------------------------------------------------------------------------
# Property 4: Validation rejects invalid OddsRecords
# Feature: oddschecker-scraper, Property 4: Validation rejects invalid OddsRecords
# Validates: Requirements 3.2, 3.3
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS = [
    "match_id", "home_team", "away_team", "starts_at",
    "market", "best_home_odds", "best_draw_odds", "best_away_odds", "fetched_at",
]

_ODDS_FIELDS = ["best_home_odds", "best_draw_odds", "best_away_odds"]


@given(
    record=valid_odds_record,
    field_to_remove=st.sampled_from(_REQUIRED_FIELDS),
)
@settings(max_examples=100)
def test_from_dict_rejects_missing_field(record: OddsRecord, field_to_remove: str):
    """from_dict raises ValueError when any required field is missing."""
    # Validates: Requirements 3.2
    d = record.to_dict()
    del d[field_to_remove]
    with pytest.raises(ValueError):
        OddsRecord.from_dict(d)


@given(
    record=valid_odds_record,
    odds_field=st.sampled_from(_ODDS_FIELDS),
    bad_value=st.one_of(
        st.floats(max_value=1.0, allow_nan=False, allow_infinity=False),
        st.just(0.0),
        st.just(-1.5),
        st.just(1.0),
    ),
)
@settings(max_examples=100)
def test_from_dict_rejects_invalid_odds(record: OddsRecord, odds_field: str, bad_value: float):
    """from_dict raises ValueError when any odds value is <= 1.0."""
    # Validates: Requirements 3.3
    d = record.to_dict()
    d[odds_field] = bad_value
    with pytest.raises(ValueError):
        OddsRecord.from_dict(d)


# ---------------------------------------------------------------------------
# Property 6: Insert payload contains all required columns
# Feature: oddschecker-scraper, Property 6: Insert payload contains all required columns
# Validates: Requirements 4.2
# ---------------------------------------------------------------------------

_REQUIRED_COLUMNS = [
    "match_id", "home_team", "away_team", "starts_at",
    "market", "best_home_odds", "best_draw_odds", "best_away_odds", "fetched_at",
]


@given(record=valid_odds_record)
@settings(max_examples=100)
def test_to_dict_contains_all_required_columns(record: OddsRecord):
    """to_dict() must contain all required column keys for Supabase insert."""
    # Validates: Requirements 4.2
    d = record.to_dict()
    for col in _REQUIRED_COLUMNS:
        assert col in d, f"Missing column: {col}"


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_to_dict_serialises_uuid_as_str():
    record = make_odds_record()
    d = record.to_dict()
    assert isinstance(d["match_id"], str)
    # Must be a valid UUID string
    UUID(d["match_id"])


def test_to_dict_serialises_datetimes_as_iso8601():
    record = make_odds_record()
    d = record.to_dict()
    assert isinstance(d["starts_at"], str)
    assert isinstance(d["fetched_at"], str)
    # Must be parseable as ISO 8601
    datetime.fromisoformat(d["starts_at"])
    datetime.fromisoformat(d["fetched_at"])


def test_from_dict_raises_on_missing_field():
    record = make_odds_record()
    d = record.to_dict()
    del d["home_team"]
    with pytest.raises(ValueError, match="home_team"):
        OddsRecord.from_dict(d)


def test_from_dict_raises_on_odds_exactly_one():
    record = make_odds_record()
    d = record.to_dict()
    d["best_home_odds"] = 1.0
    with pytest.raises(ValueError):
        OddsRecord.from_dict(d)


def test_from_dict_raises_on_odds_below_one():
    record = make_odds_record()
    d = record.to_dict()
    d["best_draw_odds"] = 0.9
    with pytest.raises(ValueError):
        OddsRecord.from_dict(d)


def test_match_dataclass_fields():
    m = Match(
        match_id=uuid4(),
        home_team="Liverpool",
        away_team="Man City",
        starts_at=datetime(2024, 9, 1, 16, 30, tzinfo=timezone.utc),
        odds_page_url="https://www.oddschecker.com/football/english/premier-league/liverpool-v-man-city/winner",
    )
    assert m.home_team == "Liverpool"
    assert m.away_team == "Man City"
    assert isinstance(m.match_id, UUID)
