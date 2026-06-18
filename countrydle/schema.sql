CREATE TABLE IF NOT EXISTS users (
    user_id      INTEGER PRIMARY KEY,
    display_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS puzzles (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    puzzle_date      TEXT UNIQUE,                     -- YYYY-MM-DD in game tz; NULL while queued
    image_path       TEXT,
    source           TEXT NOT NULL DEFAULT 'commons',
    source_id        TEXT,                            -- Commons page id / file title
    author           TEXT,
    license          TEXT,
    attribution_url  TEXT,
    answer_iso       TEXT NOT NULL,                   -- ISO 3166-1 alpha-2
    answer_lat       REAL NOT NULL,
    answer_lon       REAL NOT NULL,
    status           TEXT NOT NULL DEFAULT 'queued',  -- queued|live|closed|voided
    message_id       INTEGER,                         -- Discord message id of the posted puzzle
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS guesses (
    puzzle_id    INTEGER NOT NULL REFERENCES puzzles(id) ON DELETE CASCADE,
    user_id      INTEGER NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    guess_iso    TEXT NOT NULL,
    distance_km  REAL NOT NULL,
    score        INTEGER NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (puzzle_id, user_id)                  -- one guess per user per puzzle
);

CREATE INDEX IF NOT EXISTS idx_guesses_user ON guesses(user_id);
CREATE INDEX IF NOT EXISTS idx_puzzles_status ON puzzles(status);
