import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def connect(path):
    """Open a SQLite connection with name-based row access and foreign keys enabled."""
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _migrate(conn):
    """Apply column additions to databases created before a schema change."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(puzzles)").fetchall()}
    if "message_id" not in columns:
        conn.execute("ALTER TABLE puzzles ADD COLUMN message_id INTEGER")


def init_db(path):
    """Create the database file (and parent dirs) and apply the schema idempotently."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    with conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        _migrate(conn)
    return conn
