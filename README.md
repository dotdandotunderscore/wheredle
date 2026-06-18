# Countrydle

A daily "guess the country" Discord game for a group of friends. Each day the bot posts a
striking, geotagged photograph sourced from Wikimedia Commons; players get **one** guess,
scored by how close their country is to the real one.

## Design at a glance

- **Photos:** Wikimedia Commons *Featured pictures* + *Quality images* (community-vetted),
  auto-filtered to those with a single, clean country location. Attribution is shown at reveal.
- **One guess/day**, distance-scored: `score = round(100 · e^(−distance_km / 2000))`,
  exact country = 100.
- **Spoiler-safe + social:** you see nothing about others until your guess is locked; the
  instant you lock it, the full board (everyone's country + distance + score) opens to you
  via your `/guess` reply and the gated `/results` command.
- **Cadence:** rolling 24h — when the next day's puzzle posts, yesterday's answer +
  attribution + leaderboard reveal.
- **Hosting:** Railway (long-running worker process). Wired up in Phase 6.

## Roadmap

1. **Scaffold + scoring** ✅ — config, SQLite schema, country/centroid data, scoring math + tests.
2. Commons sourcing + reverse-geocode + auto-qualify filters.
3. Core game: `/guess` (autocomplete + confirm), scoring, gated `/results` board.
4. Daily scheduler: auto-post + reveal-previous with attribution.
5. Leaderboards, streaks, share text, 🚩 report + admin `/skip`.
6. Deploy to Railway (`Procfile`), EXIF strip/resize polish.

## Phase 1 setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

python scripts/build_countries.py   # writes data/countries.csv (needs internet, one-off)
python -m pytest                     # run the test suite

cp .env.example .env                 # then fill in DISCORD_TOKEN etc.
python scripts/init_db.py            # create data/game.db
```

`main.py` starts the bot (no game commands yet — those arrive in Phase 3).
