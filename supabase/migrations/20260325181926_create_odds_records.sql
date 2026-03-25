create table if not exists odds_records (
    id            bigserial primary key,
    match_id      uuid        not null,
    home_team     text        not null,
    away_team     text        not null,
    starts_at     timestamptz not null,
    market        text        not null default 'Match Result',
    best_home_odds numeric(6,3) not null check (best_home_odds > 1.0),
    best_draw_odds numeric(6,3) not null check (best_draw_odds > 1.0),
    best_away_odds numeric(6,3) not null check (best_away_odds > 1.0),
    fetched_at    timestamptz not null default now(),
    created_at    timestamptz not null default now()
);

-- Index for common query patterns
create index if not exists idx_odds_records_match_id   on odds_records (match_id);
create index if not exists idx_odds_records_starts_at on odds_records (starts_at desc);
create index if not exists idx_odds_records_fetched_at on odds_records (fetched_at desc);
