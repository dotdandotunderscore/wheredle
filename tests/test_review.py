import asyncio
import sqlite3

import pytest

from wheredle.cogs.daily import DailyCog, LOW_QUEUE_THRESHOLD
from wheredle.db import init_db
from wheredle.game import repository as repo


class _FakeChannel:
    def __init__(self):
        self.sent = []

    async def send(self, content, **kwargs):
        self.sent.append(content)


@pytest.fixture
def conn(tmp_path):
    return init_db(str(tmp_path / "test.db"))


def _pending(conn, pid, review_message_id=None):
    conn.execute(
        """INSERT INTO puzzles (id, image_path, source, source_id, answer_iso, answer_lat,
                                answer_lon, status, review_message_id)
           VALUES (?, 'url', 'commons', ?, 'FR', 46.0, 2.0, 'pending', ?)""",
        (pid, str(pid), review_message_id),
    )
    conn.commit()


def _status(conn, pid):
    return conn.execute("SELECT status FROM puzzles WHERE id=?", (pid,)).fetchone()["status"]


def test_new_candidates_are_pending_not_queued(conn):
    from wheredle.sourcing.candidates import queue_candidate

    candidate = {
        "pageid": 42,
        "image_url": "http://example/x.jpg",
        "author": "A",
        "license": "CC0",
        "attribution_url": "http://example",
    }
    with conn:
        assert queue_candidate(conn, candidate, "FR") is True
    assert _status(conn, conn.execute("SELECT id FROM puzzles").fetchone()["id"]) == "pending"


def test_unposted_pending_excludes_already_posted(conn):
    _pending(conn, 1)
    _pending(conn, 2, review_message_id=999)
    ids = [p["id"] for p in repo.get_unposted_pending(conn)]
    assert ids == [1]


def test_approve_promotes_to_queued(conn):
    _pending(conn, 1, review_message_id=100)
    assert repo.approve_puzzle(conn, 1) is True
    assert _status(conn, 1) == "queued"


def test_reject_marks_rejected(conn):
    _pending(conn, 1, review_message_id=100)
    assert repo.reject_puzzle(conn, 1) is True
    assert _status(conn, 1) == "rejected"


def test_vote_is_idempotent_once_resolved(conn):
    _pending(conn, 1, review_message_id=100)
    repo.approve_puzzle(conn, 1)
    # A second vote lands on a row that is no longer pending, so it is ignored.
    assert repo.get_pending_by_review_message(conn, 100) is None
    assert repo.reject_puzzle(conn, 1) is False
    assert _status(conn, 1) == "queued"


def test_rejected_image_is_never_requeued(conn):
    from wheredle.sourcing.candidates import queue_candidate

    _pending(conn, 1)
    repo.reject_puzzle(conn, 1)
    candidate = {
        "pageid": 1,  # same source_id as the rejected row
        "image_url": "http://example/x.jpg",
        "author": "A",
        "license": "CC0",
        "attribution_url": "http://example",
    }
    with conn:
        assert queue_candidate(conn, candidate, "FR") is False


def test_queue_depth_counts_ready_and_pending(conn):
    _pending(conn, 1)
    _pending(conn, 2)
    repo.approve_puzzle(conn, 2)
    ready, pending = repo.queue_depth(conn)
    assert (ready, pending) == (1, 1)


def test_migration_sends_legacy_queue_through_review(tmp_path):
    path = str(tmp_path / "legacy.db")
    # Simulate a pre-review DB: a puzzles table with no review_message_id column.
    legacy = sqlite3.connect(path)
    legacy.execute(
        """CREATE TABLE puzzles (
               id INTEGER PRIMARY KEY, image_path TEXT, source TEXT NOT NULL DEFAULT 'commons',
               answer_iso TEXT NOT NULL, answer_lat REAL NOT NULL, answer_lon REAL NOT NULL,
               status TEXT NOT NULL DEFAULT 'queued')"""
    )
    legacy.execute(
        "INSERT INTO puzzles (id, image_path, answer_iso, answer_lat, answer_lon, status)"
        " VALUES (1, 'url', 'FR', 46.0, 2.0, 'queued')"
    )
    legacy.commit()
    legacy.close()

    conn = init_db(path)
    assert _status(conn, 1) == "pending"
    # A second startup must not disturb rows that have since been approved.
    repo.approve_puzzle(conn, 1)
    conn.close()
    conn = init_db(path)
    assert _status(conn, 1) == "queued"


def test_low_queue_alert_fires_once_then_rearms(conn):
    cog = DailyCog.__new__(DailyCog)  # skip __init__ (no bot/loops needed)
    cog._low_queue_alerted = False
    channel = _FakeChannel()

    # 0 approved → below threshold → one ping.
    asyncio.run(cog._alert_if_low(conn, channel))
    assert len(channel.sent) == 1
    assert "@everyone" in channel.sent[0]

    # Still low → no repeat ping.
    asyncio.run(cog._alert_if_low(conn, channel))
    assert len(channel.sent) == 1

    # Approve back above the threshold → arms the next alert (no ping now).
    for pid in range(1, LOW_QUEUE_THRESHOLD + 1):
        _pending(conn, pid)
        repo.approve_puzzle(conn, pid)
    asyncio.run(cog._alert_if_low(conn, channel))
    assert len(channel.sent) == 1

    # Drop below again (one approved puzzle goes live) → pings once more.
    conn.execute("UPDATE puzzles SET status='live' WHERE id=1")
    conn.commit()
    asyncio.run(cog._alert_if_low(conn, channel))
    assert len(channel.sent) == 2
