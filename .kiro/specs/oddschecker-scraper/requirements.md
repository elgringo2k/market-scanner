# Requirements Document

## Introduction

A backend scraper that periodically fetches betting odds data for Premier League football matches from OddsChecker and persists the results in a Supabase database. The MVP scope covers Premier League matches and the Match Result (1X2) market only. The system is implemented in Python and runs as a standalone script or scheduled job. The Supabase schema will be designed from scratch as part of this spec.

OddsChecker is a React single-page application (SPA); plain HTTP requests cannot render its content. The scraper therefore uses Playwright (headless Chromium) to render pages after JavaScript execution and extract data from the DOM. Odds are stored as best-available across all bookmakers (one record per match per run), not per bookmaker.

## Glossary

- **Scraper**: The Python component responsible for rendering OddsChecker pages via Playwright and extracting odds data from the DOM
- **Playwright**: The headless browser automation library used to render JavaScript-heavy pages
- **OddsChecker**: The third-party website (oddschecker.com) that aggregates betting odds from multiple bookmakers
- **Odds_Record**: A single snapshot of the best available odds for a given match and market at a point in time; contains one best-odds value per selection (home/draw/away) derived by taking the maximum across all listed bookmakers
- **Match**: A Premier League football fixture identified by home team, away team, and kick-off date/time; each Match is assigned a UUID as its unique identifier
- **match_id**: A UUID auto-generated at scrape time to uniquely identify a Match; not derived from team names or kick-off time
- **Market**: A betting market type, e.g. Match Result (1X2), Both Teams to Score, Over/Under Goals
- **Bookmaker**: A betting operator whose odds are listed on OddsChecker (e.g. Bet365, William Hill); individual bookmaker rows are used only to derive best odds and are not stored
- **Supabase_Client**: The component responsible for writing data to the Supabase PostgreSQL database
- **Scheduler**: The component responsible for triggering scrape runs on a defined interval
- **Run**: A single end-to-end execution of the Scraper for all available Premier League matches
- **Parser**: The component that transforms rendered DOM content into structured Match and Odds_Record objects
- **Pretty_Printer**: The component that serialises structured objects back into a canonical string representation for debugging and round-trip validation

---

## Requirements

### Requirement 1: Discover Premier League Matches

**User Story:** As a data engineer, I want the scraper to discover all currently listed Premier League matches on OddsChecker, so that odds are collected for every available fixture without manual configuration.

#### Acceptance Criteria

1. WHEN a Run is initiated, THE Scraper SHALL use Playwright to render the OddsChecker Premier League football odds listing page with JavaScript fully executed
2. WHEN the listing page is rendered successfully, THE Parser SHALL extract a list of Matches including home team, away team, kick-off date/time, and the match-specific odds page URL for each fixture
3. IF the listing page fails to render or returns an error response, THEN THE Scraper SHALL log the failure reason and abort the Run with a non-zero exit code
4. IF no Matches are found on the listing page, THEN THE Scraper SHALL log a warning and abort the Run without writing to Supabase

---

### Requirement 2: Scrape Best Odds for Each Match

**User Story:** As a data engineer, I want the scraper to collect the best available odds across all bookmakers for each discovered match, so that I have a compact best-odds snapshot per run without per-bookmaker noise.

#### Acceptance Criteria

1. WHEN a Match is discovered, THE Scraper SHALL use Playwright to render the OddsChecker /winner odds page for that Match with JavaScript fully executed
2. WHEN an odds page is rendered successfully, THE Parser SHALL extract the Match Result (1X2) market odds for every listed Bookmaker from the DOM
3. WHEN Bookmaker odds have been extracted, THE Parser SHALL derive best_home_odds, best_draw_odds, and best_away_odds by taking the maximum decimal value across all Bookmakers for each selection
4. WHEN an odds page is rendered successfully, THE Parser SHALL record the UTC timestamp at which the odds were fetched
5. IF an odds page fails to render or returns an error response, THEN THE Scraper SHALL log the Match identifier and failure reason, skip that Match, and continue processing remaining Matches
6. IF the Parser cannot extract any Bookmaker odds from a rendered page, THEN THE Scraper SHALL log a warning for that Match and continue processing remaining Matches

---

### Requirement 3: Parse and Validate Odds Data

**User Story:** As a data engineer, I want all scraped odds to be validated before storage, so that corrupt or malformed data does not enter the database.

#### Acceptance Criteria

1. THE Parser SHALL produce Odds_Record objects containing: match_id (UUID), home_team, away_team, kickoff_at, market name, best_home_odds, best_draw_odds, best_away_odds, and fetched_at timestamp
2. IF an Odds_Record is missing any required field, THEN THE Parser SHALL discard that record and log the missing field name
3. IF any best-odds value is not a positive decimal number greater than 1.0, THEN THE Parser SHALL discard the affected Odds_Record and log the invalid value
4. THE Pretty_Printer SHALL serialise any Odds_Record into a canonical JSON string
5. FOR ALL valid Odds_Record objects, parsing the Pretty_Printer output SHALL produce an equivalent Odds_Record (round-trip property)

---

### Requirement 4: Persist Odds Data to Supabase

**User Story:** As a data engineer, I want scraped odds to be stored in Supabase, so that I can query historical odds and build downstream analytics.

#### Acceptance Criteria

1. WHEN a Run produces valid Odds_Records, THE Supabase_Client SHALL insert all records into the designated odds table in a single batch operation per Run
2. THE Supabase_Client SHALL store each Odds_Record with the following columns: match_id (UUID, auto-generated), home_team, away_team, kickoff_at, market, best_home_odds, best_draw_odds, best_away_odds, fetched_at
3. IF the Supabase batch insert fails, THEN THE Supabase_Client SHALL log the error message and retry the insert once after a 5-second delay
4. IF the retry also fails, THEN THE Supabase_Client SHALL log the final error and exit with a non-zero exit code without silently discarding data
5. THE Supabase_Client SHALL use the Supabase service role key sourced from an environment variable and SHALL NOT hardcode credentials in source code

---

### Requirement 5: Scheduled Execution

**User Story:** As a data engineer, I want the scraper to run automatically on a defined interval, so that odds data is kept up to date without manual intervention.

#### Acceptance Criteria

1. THE Scheduler SHALL trigger a Run at a configurable interval specified in minutes via an environment variable
2. WHEN a Run is already in progress, THE Scheduler SHALL skip the next scheduled trigger and log a warning rather than starting a concurrent Run
3. IF the interval environment variable is not set, THEN THE Scheduler SHALL default to a 10-minute interval
4. THE Scheduler SHALL log the start time and end time of each Run

---

### Requirement 6: Respectful and Resilient Browser Behaviour

**User Story:** As a data engineer, I want the scraper to behave like a real browser toward OddsChecker's servers and handle transient failures gracefully, so that the scraper avoids bot detection and data collection is reliable.

#### Acceptance Criteria

1. THE Scraper SHALL wait a configurable delay in seconds between consecutive Playwright page renders, defaulting to 2 seconds if not configured
2. THE Scraper SHALL configure Playwright with realistic browser headers and a non-headless-identifying User-Agent string to reduce the likelihood of Cloudflare or bot-detection blocks
3. THE Scraper SHALL use Playwright's stealth configuration (e.g. playwright-stealth or equivalent) to suppress detectable headless-browser signals and simulate human-like browsing behaviour
4. IF a page render results in a Cloudflare challenge page or HTTP 429/503 response, THEN THE Scraper SHALL wait 30 seconds and retry the render once before skipping that page
5. THE Scraper SHALL enforce a configurable page-load timeout, defaulting to 15 seconds, and treat a timeout as a failed render

---

### Requirement 7: Observability and Logging

**User Story:** As a data engineer, I want structured logs for every run, so that I can diagnose failures and monitor scraper health.

#### Acceptance Criteria

1. THE Scraper SHALL emit structured JSON log lines to stdout for every significant event: run start, match discovered, odds fetched, record discarded, insert success, insert failure, run end
2. WHEN a Run completes successfully, THE Scraper SHALL log a summary containing: total matches processed, total Odds_Records inserted, total records discarded, and run duration in seconds
3. THE Scraper SHALL support a configurable log level (DEBUG, INFO, WARNING, ERROR) via an environment variable, defaulting to INFO
