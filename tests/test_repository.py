import pytest

from countrydle.db import init_db
from countrydle.game import repository as repo


@pytest.fixture
def conn(tmp_path):
    connection = init_db(str(tmp_path / "test.db"))
    connection.execute(
        """INSERT INTO puzzles (id, image_path, source, answer_iso, answer_lat, answer_lon, status, puzzle_date)
           VALUES (1, 'url', 'commons', 'FR', 46.0, 2.0, 'live', '2026-01-01')"""
    )
    connection.commit()
    return connection


def _puzzle(conn):
    return repo.get_live_puzzle(conn)


def test_exact_guess_scores_full(conn):
    result = repo.record_guess(conn, _puzzle(conn), 1, "Alice", "FR")
    assert result["exact"] is True
    assert result["score"] == 100
    assert result["distance_km"] == 0.0


def test_far_guess_scores_low(conn):
    result = repo.record_guess(conn, _puzzle(conn), 2, "Bob", "AU")
    assert result["exact"] is False
    assert result["distance_km"] > 10000
    assert result["score"] < 100


def test_one_guess_per_user(conn):
    repo.record_guess(conn, _puzzle(conn), 1, "Alice", "FR")
    with pytest.raises(repo.AlreadyGuessed):
        repo.record_guess(conn, _puzzle(conn), 1, "Alice", "DE")


def test_has_guessed(conn):
    assert repo.has_guessed(conn, 1, 1) is False
    repo.record_guess(conn, _puzzle(conn), 1, "Alice", "FR")
    assert repo.has_guessed(conn, 1, 1) is True


def test_board_ranked_by_score(conn):
    repo.record_guess(conn, _puzzle(conn), 1, "Alice", "FR")  # exact, 100
    repo.record_guess(conn, _puzzle(conn), 2, "Bob", "AU")    # far, low
    rows = repo.board(conn, 1)
    assert [r["display_name"] for r in rows] == ["Alice", "Bob"]
    assert rows[0]["score"] == 100
