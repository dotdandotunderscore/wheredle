# Wheredle

A daily "guess the country" Discord game for a group of friends. Each day the bot posts a
striking, geotagged photograph sourced from Wikimedia Commons; players get **one** guess,
scored by how close their country is to the real one.

## Design at a glance

- **Photos:** Wikimedia Commons *Quality images*, sampled per-country from a balanced random
  subset of nations each run so no region dominates, then auto-filtered to those with a single,
  clean country location. Attribution is shown at reveal.
- **Human review gate:** auto-qualified candidates land in a `pending` state and are posted to a
  private review channel (location hidden) where an admin reacts ✅/❌. Only approved photos enter
  the live queue, so bad images are caught before anyone plays. Rejected images are never re-queued.
- **One guess/day**, distance-scored: `score = round(100 · e^(−distance_km / 4000))`,
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

## Railway deploy

1. Create a Railway project and link the repo.
2. Add a **Volume** in the Railway dashboard, mounted at `/data`.
3. Set environment variables (Settings → Variables):

| Variable | Example |
|---|---|
| `DISCORD_TOKEN` | your bot token |
| `GUILD_ID` | your server ID |
| `CHANNEL_ID` | the game channel ID |
| `REVIEW_CHANNEL_ID` | private channel where admins vet candidates (✅/❌) |
| `ADMIN_IDS` | comma-separated user IDs |
| `TIMEZONE` | `Europe/London` |
| `POST_HOUR` | `9` |
| `DATABASE_PATH` | `/data/game.db` |

4. On first deploy, initialise the database and seed the queue:

```bash
railway run python scripts/init_db.py
railway run python scripts/fetch_candidates.py
```

The bot tops up daily, fetching new candidates whenever fewer than 20 puzzles are approved or
awaiting review, and posts un-reviewed ones to `REVIEW_CHANNEL_ID` for an admin to ✅/❌.

## Discord bot setup

When creating the bot application, use these OAuth2 settings:

**Scopes:** `bot`, `applications.commands`

**Bot permissions:** Send Messages, Embed Links, Attach Files, Add Reactions, Read Message History, Manage Messages

No privileged gateway intents are required.

https://discord.com/oauth2/authorize?client_id=1517088110180171888&permissions=124992&integration_type=0&scope=bot+applications.commands

## Phase 1 setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

python scripts/build_countries.py            # writes data/countries.csv (needs internet, one-off)
python scripts/build_commons_categories.py   # writes data/commons_categories.csv (needs internet, one-off)
python -m pytest                             # run the test suite

cp .env.example .env                 # then fill in DISCORD_TOKEN etc.
python scripts/init_db.py            # create data/game.db
```

`main.py` starts the bot (no game commands yet — those arrive in Phase 3).

## SSHing in
Railway container builder creates a venv for the bot at /opt/venv/bin.
After sshing in, use `source /opt/venv/bin/activate` to use the same venv as the bot while running scripts