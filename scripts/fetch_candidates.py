import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from countrydle.config import Config
from countrydle.db import init_db
from countrydle.game import countries
from countrydle.sourcing.candidates import gather, queue_candidate


def main():
    """Fetch Commons candidates, qualify them, and queue new ones into the puzzle pool."""
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    config = Config.from_env()
    conn = init_db(config.database_path)

    qualified = gather(limit_per_category=limit)
    added = 0
    with conn:
        for candidate, iso2 in qualified:
            if queue_candidate(conn, candidate, iso2):
                added += 1
                print(f"  + {countries.get(iso2).name:<20} {candidate['title']}")

    queued = conn.execute("SELECT COUNT(*) FROM puzzles WHERE status='queued'").fetchone()[0]
    print(f"\nqualified {len(qualified)}, added {added} new -> {queued} queued puzzles")
    return 0


if __name__ == "__main__":
    sys.exit(main())
