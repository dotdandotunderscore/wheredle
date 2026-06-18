import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from countrydle.config import Config
from countrydle.db import init_db


def main():
    """Create the SQLite database and apply the schema."""
    config = Config.from_env()
    init_db(config.database_path)
    print(f"initialised database at {config.database_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
