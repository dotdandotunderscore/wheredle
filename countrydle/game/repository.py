import sqlite3

from . import countries
from .scoring import score_for_distance


class AlreadyGuessed(Exception):
    """Raised when a user tries to guess a puzzle they have already guessed."""


def get_live_puzzle(conn):
    """Return the currently live puzzle row, or None."""
    return conn.execute(
        "SELECT * FROM puzzles WHERE status='live' ORDER BY puzzle_date DESC LIMIT 1"
    ).fetchone()


def get_puzzle(conn, puzzle_id):
    """Return a puzzle row by id, or None."""
    return conn.execute("SELECT * FROM puzzles WHERE id=?", (puzzle_id,)).fetchone()


def activate_puzzle(conn, puzzle_id, puzzle_date):
    """Mark a queued puzzle as live for a given date (used by the daily scheduler)."""
    with conn:
        conn.execute(
            "UPDATE puzzles SET status='live', puzzle_date=? WHERE id=?",
            (puzzle_date, puzzle_id),
        )


def rotate_daily(conn, today):
    """Close the live puzzle and promote the oldest queued puzzle to live for `today`.

    Returns (closed_puzzle_or_None, new_puzzle_or_None). The closed row is a pre-update
    snapshot, so it still carries the answer/attribution needed to build the reveal.
    """
    with conn:
        closed = get_live_puzzle(conn)
        if closed is not None:
            conn.execute("UPDATE puzzles SET status='closed' WHERE id=?", (closed["id"],))
        new = conn.execute(
            "SELECT * FROM puzzles WHERE status='queued' ORDER BY id LIMIT 1"
        ).fetchone()
        if new is not None:
            conn.execute(
                "UPDATE puzzles SET status='live', puzzle_date=? WHERE id=?",
                (today, new["id"]),
            )
    refreshed = get_puzzle(conn, new["id"]) if new is not None else None
    return closed, refreshed


def has_guessed(conn, puzzle_id, user_id):
    """Return True if the user has already locked a guess for this puzzle."""
    row = conn.execute(
        "SELECT 1 FROM guesses WHERE puzzle_id=? AND user_id=?", (puzzle_id, user_id)
    ).fetchone()
    return row is not None


def _ensure_user(conn, user_id, display_name):
    """Insert or update a user's display name."""
    conn.execute(
        """INSERT INTO users (user_id, display_name) VALUES (?, ?)
           ON CONFLICT(user_id) DO UPDATE SET display_name=excluded.display_name""",
        (user_id, display_name),
    )


def record_guess(conn, puzzle, user_id, display_name, guess_iso):
    """Score and store a one-per-day guess; return a result dict.

    Raises AlreadyGuessed if the user has already guessed this puzzle.
    """
    answer_iso = puzzle["answer_iso"]
    exact = guess_iso == answer_iso
    distance = 0.0 if exact else countries.distance_between(guess_iso, answer_iso)
    score = score_for_distance(distance, exact=exact)
    try:
        with conn:
            _ensure_user(conn, user_id, display_name)
            conn.execute(
                """INSERT INTO guesses (puzzle_id, user_id, guess_iso, distance_km, score)
                   VALUES (?, ?, ?, ?, ?)""",
                (puzzle["id"], user_id, guess_iso, distance, score),
            )
    except sqlite3.IntegrityError as exc:
        raise AlreadyGuessed() from exc
    return {"guess_iso": guess_iso, "distance_km": distance, "score": score, "exact": exact}


def get_guess(conn, puzzle_id, user_id):
    """Return a user's guess row for a puzzle, or None."""
    return conn.execute(
        "SELECT * FROM guesses WHERE puzzle_id=? AND user_id=?", (puzzle_id, user_id)
    ).fetchone()


def void_live(conn, today):
    """Void the live puzzle and promote the next queued one (admin skip / auto-report).

    Unlike rotate_daily this does not reveal the voided puzzle. Returns the new puzzle or None.
    """
    with conn:
        live = get_live_puzzle(conn)
        if live is not None:
            conn.execute("UPDATE puzzles SET status='voided', puzzle_date=NULL WHERE id=?", (live["id"],))
        new = conn.execute(
            "SELECT * FROM puzzles WHERE status='queued' ORDER BY id LIMIT 1"
        ).fetchone()
        if new is not None:
            conn.execute(
                "UPDATE puzzles SET status='live', puzzle_date=? WHERE id=?",
                (today, new["id"]),
            )
    return get_puzzle(conn, new["id"]) if new is not None else None


def set_message_id(conn, puzzle_id, message_id):
    """Record the Discord message id of a posted puzzle (for report-react tracking)."""
    with conn:
        conn.execute("UPDATE puzzles SET message_id=? WHERE id=?", (message_id, puzzle_id))


def leaderboard(conn, since=None, limit=15):
    """Return ranked totals per user, optionally only counting puzzles on/after `since`."""
    query = """SELECT u.display_name,
                      SUM(g.score) AS total,
                      COUNT(*) AS played,
                      CAST(ROUND(AVG(g.score)) AS INTEGER) AS average
               FROM guesses g
               JOIN users u ON u.user_id = g.user_id
               JOIN puzzles p ON p.id = g.puzzle_id"""
    params = []
    if since is not None:
        query += " WHERE p.puzzle_date >= ?"
        params.append(since)
    query += " GROUP BY g.user_id ORDER BY total DESC, played ASC LIMIT ?"
    params.append(limit)
    return [dict(row) for row in conn.execute(query, params).fetchall()]


def current_streak(conn, user_id):
    """Count consecutive puzzle days (ending at the most recent) the user guessed on."""
    days = conn.execute(
        """SELECT puzzle_date FROM puzzles
           WHERE status IN ('live', 'closed') AND puzzle_date IS NOT NULL
           ORDER BY puzzle_date DESC"""
    ).fetchall()
    guessed = {
        row["puzzle_date"]
        for row in conn.execute(
            """SELECT p.puzzle_date FROM guesses g
               JOIN puzzles p ON p.id = g.puzzle_id
               WHERE g.user_id = ? AND p.puzzle_date IS NOT NULL""",
            (user_id,),
        ).fetchall()
    }
    streak = 0
    for row in days:
        if row["puzzle_date"] in guessed:
            streak += 1
        else:
            break
    return streak


def user_stats(conn, user_id):
    """Return a user's aggregate stats: games played, total/average/best score, current streak."""
    row = conn.execute(
        """SELECT COUNT(*) AS played,
                  COALESCE(SUM(score), 0) AS total,
                  COALESCE(CAST(ROUND(AVG(score)) AS INTEGER), 0) AS average,
                  COALESCE(MAX(score), 0) AS best
           FROM guesses WHERE user_id=?""",
        (user_id,),
    ).fetchone()
    stats = dict(row)
    stats["streak"] = current_streak(conn, user_id)
    return stats


def board(conn, puzzle_id):
    """Return all guesses for a puzzle, ranked by score then time, as dicts."""
    rows = conn.execute(
        """SELECT u.display_name, g.guess_iso, g.distance_km, g.score
           FROM guesses g JOIN users u ON u.user_id = g.user_id
           WHERE g.puzzle_id = ?
           ORDER BY g.score DESC, g.created_at ASC""",
        (puzzle_id,),
    ).fetchall()
    return [dict(row) for row in rows]
