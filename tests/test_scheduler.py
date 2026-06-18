import pytest

from countrydle.db import init_db
from countrydle.game import repository as repo


@pytest.fixture
def conn(tmp_path):
    connection = init_db(str(tmp_path / "test.db"))
    for pid in (1, 2):
        connection.execute(
            """INSERT INTO puzzles (id, image_path, source, answer_iso, answer_lat, answer_lon, status)
               VALUES (?, 'url', 'commons', 'FR', 46.0, 2.0, 'queued')""",
            (pid,),
        )
    connection.commit()
    return connection


def _status(conn, pid):
    return conn.execute("SELECT status FROM puzzles WHERE id=?", (pid,)).fetchone()["status"]


def test_first_rotation_has_no_reveal(conn):
    closed, new = repo.rotate_daily(conn, "2026-01-01")
    assert closed is None
    assert new["id"] == 1
    assert _status(conn, 1) == "live"


def test_second_rotation_closes_previous(conn):
    repo.rotate_daily(conn, "2026-01-01")
    closed, new = repo.rotate_daily(conn, "2026-01-02")
    assert closed["id"] == 1
    assert new["id"] == 2
    assert _status(conn, 1) == "closed"
    assert _status(conn, 2) == "live"
    assert new["puzzle_date"] == "2026-01-02"


def test_rotation_without_queue_warns(conn):
    repo.rotate_daily(conn, "2026-01-01")
    repo.rotate_daily(conn, "2026-01-02")
    closed, new = repo.rotate_daily(conn, "2026-01-03")
    assert closed["id"] == 2
    assert new is None
