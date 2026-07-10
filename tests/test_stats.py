import pytest

from wheredle.db import init_db
from wheredle.game import repository as repo
from wheredle.game.share import score_square, share_text


@pytest.fixture
def conn(tmp_path):
    connection = init_db(str(tmp_path / "test.db"))
    # Three closed puzzles on consecutive days.
    for pid, day in ((1, "2026-01-01"), (2, "2026-01-02"), (3, "2026-01-03")):
        connection.execute(
            """INSERT INTO puzzles (id, image_path, source, answer_iso, answer_lat, answer_lon, status, puzzle_date)
               VALUES (?, 'url', 'commons', 'FR', 46.0, 2.0, 'closed', ?)""",
            (pid, day),
        )
    connection.executemany(
        "INSERT INTO users (user_id, display_name) VALUES (?, ?)",
        [(1, "Alice"), (2, "Bob")],
    )
    # Alice plays all three days; Bob plays days 1 and 3 (gap on day 2).
    guesses = [
        (1, 1, "FR", 0, 100), (2, 1, "FR", 0, 100), (3, 1, "FR", 0, 100),
        (1, 2, "DE", 400, 80), (3, 2, "DE", 400, 80),
    ]
    connection.executemany(
        "INSERT INTO guesses (puzzle_id, user_id, guess_iso, distance_km, score) VALUES (?, ?, ?, ?, ?)",
        guesses,
    )
    connection.commit()
    return connection


def test_leaderboard_ranks_by_total(conn):
    rows = repo.leaderboard(conn)
    assert [r["display_name"] for r in rows] == ["Alice", "Bob"]
    assert rows[0]["total"] == 300
    assert rows[0]["played"] == 3
    assert rows[1]["total"] == 160


def test_streak_counts_consecutive_days(conn):
    assert repo.current_streak(conn, 1) == 3   # Alice: all three days
    assert repo.current_streak(conn, 2) == 1   # Bob: day 3 only, day 2 breaks it


def test_user_stats(conn):
    stats = repo.user_stats(conn, 1)
    assert stats == {"played": 3, "total": 300, "average": 100, "best": 100, "streak": 3}


def test_leaderboard_paginates_with_offset(conn):
    page1 = repo.leaderboard(conn, limit=1, offset=0)
    page2 = repo.leaderboard(conn, limit=1, offset=1)
    assert [r["display_name"] for r in page1] == ["Alice"]
    assert [r["display_name"] for r in page2] == ["Bob"]
    assert repo.leaderboard(conn, limit=1, offset=2) == []  # past the end


def test_leaderboard_size_counts_players(conn):
    assert repo.leaderboard_size(conn) == 2
    assert repo.leaderboard_size(conn, since="2026-01-03") == 2


def test_leaderboard_since_filters(conn):
    rows = repo.leaderboard(conn, since="2026-01-03")
    totals = {r["display_name"]: r["total"] for r in rows}
    assert totals == {"Alice": 100, "Bob": 80}


def test_share_text_and_squares():
    assert score_square(100) == "🟩"
    assert score_square(50) == "🟧"
    assert score_square(5) == "🟥"
    assert "100/100" in share_text("2026-01-01", 100, 0, True)
    assert "412 km" in share_text("2026-01-01", 80, 412.3, False)
