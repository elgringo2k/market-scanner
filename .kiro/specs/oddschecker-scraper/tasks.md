# Implementation Plan: oddschecker-scraper

## Overview

Implement a Python scraper that periodically fetches Premier League odds from OddsChecker via Playwright and persists best-available odds snapshots to Supabase. Tasks follow the component order from the design: scaffolding → schema → models → logger → scraper → parser → Supabase client → runner → scheduler → entry point → tests.

## Tasks

- [x] 1. Sdxaswswcaffold project structure and configuration files
  - Create `src/`, `tests/`, `supabase/migrations/` directories
  - Create `requirements.txt` with pinned dependencies: `playwright`, `playwright-stealth`, `supabase`, `apscheduler`, `python-dotenv`, `python-json-logger`, `hypothesis`, `pytest`, `pytest-asyncio`, `beautifulsoup4`, `lxml`
  - Create `.env.example` with all env vars: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `POLL_INTERVAL_MINUTES`, `PAGE_DELAY_SECONDS`, `PAGE_TIMEOUT_SECONDS`, `LOG_LEVEL`
  - Create `Dockerfile` using `mcr.microsoft.com/playwright/python:v1.44.0-jammy` base image as specified in design
  - _Requirements: 4.5, 5.1, 6.1, 7.3_

- [x] 2. Create Supabase SQL migration
  - Create `supabase/migrations/<timestamp>_create_odds_records.sql` with the `odds_records` table definition from the design
  - Include `bigserial` primary key, all required columns with correct types, `check` constraints for odds > 1.0, and the three indexes on `match_id`, `kickoff_at`, `fetched_at`
  - _Requirements: 4.2_

- [x] 3. Implement data models
  - Create `src/models.py` with `Match` and `OddsRecord` dataclasses exactly as specified in the design
  - Implement `OddsRecord.to_dict()` serialising all fields to JSON-compatible types (UUID → str, datetime → ISO 8601 string)
  - Implement `OddsRecord.from_dict()` deserialising from a dict, raising `ValueError` if any required field is missing or any odds value is ≤ 1.0
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x]* 3.1 Write property test for OddsRecord round-trip (Property 5)
    - **Property 5: OddsRecord serialisation round-trip**
    - Use `st.builds(OddsRecord, ...)` with valid field strategies; assert `from_dict(to_dict(record)) == record`
    - **Validates: Requirements 3.4, 3.5**

  - [x]* 3.2 Write property test for validation rejection (Property 4)
    - **Property 4: Validation rejects invalid OddsRecords**
    - Generate dicts with at least one missing required field or any odds value ≤ 1.0; assert `from_dict` raises
    - **Validates: Requirements 3.2, 3.3**

  - [x]* 3.3 Write property test for insert payload columns (Property 6)
    - **Property 6: Insert payload contains all required columns**
    - Generate valid `OddsRecord` instances; assert `to_dict()` contains all required column keys
    - **Validates: Requirements 4.2**

- [x] 4. Implement structured JSON logger
  - Create `src/logger.py` that configures `python-json-logger` on the root logger
  - Read `LOG_LEVEL` from env (default `INFO`) and apply it at configuration time
  - Expose a `get_logger(name: str) -> logging.Logger` factory used by all other modules
  - _Requirements: 7.1, 7.3_

  - [x]* 4.1 Write property test for JSON log output (Property 7)
    - **Property 7: All log output is valid JSON**
    - Capture log handler output for randomly generated event dicts; assert `json.loads(line)` does not raise
    - **Validates: Requirements 7.1**

- [x] 5. Implement Scraper component
  - Create `src/scraper.py` with an async `Scraper` class managing the Playwright browser lifecycle
  - Implement `fetch_listing_page() -> str` and `fetch_odds_page(url: str) -> str` as specified in the design
  - Apply `playwright-stealth`, realistic `User-Agent`, and `--disable-blink-features=AutomationControlled` launch arg
  - Implement configurable inter-request delay (`PAGE_DELAY_SECONDS`, default 2 s) and page-load timeout (`PAGE_TIMEOUT_SECONDS`, default 15 s)
  - Detect Cloudflare challenge / HTTP 429 / 503 responses → wait 30 s and retry once; raise `ScraperError` on second failure
  - Treat page-load timeout as a failed render and raise `ScraperError`
  - _Requirements: 1.1, 2.1, 6.1, 6.2, 6.3, 6.4, 6.5_

- [ ] 6. Implement Parser component
  - Create `src/parser.py` with `parse_listing_page(html: str) -> list[Match]` and `parse_odds_page(html: str, match: Match) -> OddsRecord | None`
  - `parse_listing_page`: extract home team, away team, kickoff datetime (UTC), and odds page URL for each fixture row; auto-generate a UUID `match_id` per match
  - `parse_odds_page`: extract all bookmaker decimal odds rows; derive best odds via `max()` per selection; validate all fields; return `None` and log on any validation failure
  - _Requirements: 1.2, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3_

  - [ ]* 6.1 Write property test for Match field extraction (Property 1)
    - **Property 1: Parser extracts all required Match fields**
    - Generate synthetic listing-page HTML with random team names, dates, and URLs; assert every returned `Match` has non-empty `home_team`, `away_team`, `kickoff_at`, `odds_page_url`, and a valid UUID `match_id`
    - **Validates: Requirements 1.2**

  - [ ]* 6.2 Write property test for best odds derivation (Property 2)
    - **Property 2: Best odds equal the maximum across bookmakers**
    - Generate lists of `(home, draw, away)` float tuples > 1.0; assert derived best odds equal `max()` of each column
    - **Validates: Requirements 2.3**

  - [ ]* 6.3 Write property test for OddsRecord field extraction (Property 3)
    - **Property 3: Parser extracts all required OddsRecord fields**
    - Generate synthetic odds-page HTML with random bookmaker rows; assert returned `OddsRecord` has non-None values for all required fields
    - **Validates: Requirements 3.1**

- [ ] 7. Implement SupabaseClient
  - Create `src/supabase_client.py` with `SupabaseClient` class
  - Implement `insert_odds_records(records: list[OddsRecord]) -> None` that calls `to_dict()` on each record and performs a single batch insert
  - On insert failure, log the error and retry once after a 5-second delay; on second failure, log the final error and raise so the runner can exit non-zero
  - Source `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` exclusively from environment variables
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 7.1 Write unit tests for SupabaseClient retry logic
    - Mock the supabase-py client; simulate first insert raising, second succeeding; assert retry is attempted
    - Simulate both inserts failing; assert exception is raised and not swallowed
    - _Requirements: 4.3, 4.4_

- [ ] 8. Implement Runner
  - Create `src/runner.py` with an async `run()` function that orchestrates a single end-to-end scrape run
  - Call `Scraper.fetch_listing_page()` → `parse_listing_page()` → abort with non-zero exit if listing fails or returns no matches
  - For each match, call `Scraper.fetch_odds_page()` → `parse_odds_page()`; log and skip on per-match failure
  - Collect all valid `OddsRecord` objects and call `SupabaseClient.insert_odds_records()`
  - Log run start, run end, and summary (total matches, records inserted, records discarded, duration)
  - _Requirements: 1.3, 1.4, 2.5, 2.6, 4.1, 7.1, 7.2_

  - [ ]* 8.1 Write unit tests for Runner error handling
    - Mock `Scraper` to raise `ScraperError` on listing page; assert run aborts and exits non-zero
    - Mock `Scraper` to return empty match list; assert run aborts without DB write
    - Mock individual match page failure; assert that match is skipped and remaining matches are processed
    - _Requirements: 1.3, 1.4, 2.5_

- [ ] 9. Checkpoint — ensure models, logger, scraper, parser, client, and runner all wire together
  - Ensure all tests written so far pass, ask the user if questions arise.

- [ ] 10. Implement Scheduler
  - Create `src/scheduler.py` using APScheduler `BlockingScheduler` with `IntervalTrigger`
  - Read `POLL_INTERVAL_MINUTES` from env (default 10); configure the interval trigger accordingly
  - Use a `threading.Event` flag to prevent concurrent runs: if a run is already in progress, log a warning and skip the trigger
  - Log run start time and end time for each triggered run
  - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ]* 10.1 Write unit tests for Scheduler concurrent-run prevention
    - Simulate a run already in progress; assert the next trigger logs a warning and does not start a second run
    - Simulate `POLL_INTERVAL_MINUTES` not set; assert scheduler defaults to 10-minute interval
    - _Requirements: 5.2, 5.3_

- [ ] 11. Implement main.py entry point
  - Create `main.py` at the project root that initialises the logger, validates required env vars (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`) at startup and raises clearly if missing, then starts the `Scheduler`
  - Load `.env` via `python-dotenv` before reading any env vars
  - _Requirements: 4.5, 5.1, 7.3_

- [ ] 12. Final checkpoint — full test suite passes
  - Ensure all tests pass, ask the user if questions arise.
