import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from countrydle.config import Config
from countrydle.db import connect


def main():
    """Wipe all queued puzzles from the database."""
    c = connect(Config.from_env().database_path)
    c.execute("DELETE FROM puzzles WHERE status='queued'")
    c.commit()
    print("done")


if __name__ == "__main__":
    main()
