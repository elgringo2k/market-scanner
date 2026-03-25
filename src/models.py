from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass
class Match:
    match_id: UUID          # auto-generated at parse time
    home_team: str
    away_team: str
    starts_at: datetime    # UTC
    odds_page_url: str      # full URL to /winner page


_REQUIRED_ODDS_FIELDS = (
    "match_id",
    "home_team",
    "away_team",
    "starts_at",
    "market",
    "best_home_odds",
    "best_draw_odds",
    "best_away_odds",
    "fetched_at",
)

_ODDS_FIELDS = ("best_home_odds", "best_draw_odds", "best_away_odds")


@dataclass
class OddsRecord:
    match_id: UUID
    home_team: str
    away_team: str
    starts_at: datetime    # UTC
    market: str             # e.g. "Match Result"
    best_home_odds: float   # max across bookmakers, > 1.0
    best_draw_odds: float
    best_away_odds: float
    fetched_at: datetime    # UTC timestamp of page render

    def to_dict(self) -> dict:
        """Serialise to a JSON-compatible dict (for Supabase insert and pretty-printing)."""
        return {
            "match_id": str(self.match_id),
            "home_team": self.home_team,
            "away_team": self.away_team,
            "starts_at": self.starts_at.isoformat(),
            "market": self.market,
            "best_home_odds": self.best_home_odds,
            "best_draw_odds": self.best_draw_odds,
            "best_away_odds": self.best_away_odds,
            "fetched_at": self.fetched_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "OddsRecord":
        """Deserialise from a dict produced by to_dict().

        Raises ValueError if any required field is missing or any odds value is <= 1.0.
        """
        for field in _REQUIRED_ODDS_FIELDS:
            if field not in data or data[field] is None:
                raise ValueError(f"Missing required field: {field}")

        for field in _ODDS_FIELDS:
            value = data[field]
            if not isinstance(value, (int, float)) or value <= 1.0:
                raise ValueError(f"Invalid odds value for {field}: {value}")

        return cls(
            match_id=UUID(data["match_id"]) if isinstance(data["match_id"], str) else data["match_id"],
            home_team=data["home_team"],
            away_team=data["away_team"],
            starts_at=datetime.fromisoformat(data["starts_at"]) if isinstance(data["starts_at"], str) else data["starts_at"],
            market=data["market"],
            best_home_odds=float(data["best_home_odds"]),
            best_draw_odds=float(data["best_draw_odds"]),
            best_away_odds=float(data["best_away_odds"]),
            fetched_at=datetime.fromisoformat(data["fetched_at"]) if isinstance(data["fetched_at"], str) else data["fetched_at"],
        )
