from __future__ import annotations

import json
import sqlite3

from app.db import connect, init_db
from app.models import CreateSessionRequest, Filters
from app.sessions import create_session


def test_create_session_returns_uuid_and_inserts_row(tmp_path) -> None:
    db = tmp_path / "t.sqlite"
    init_db(db)
    conn = connect(db)
    try:
        req = CreateSessionRequest(
            mode="time", target=5, auto_advance=True, dedupe_solved=True,
            filters=Filters(rating_min=1500, rating_max=1800),
            label="my session",
        )
        result = create_session(conn, req)

        assert isinstance(result.session_id, str)
        assert len(result.session_id) == 36  # UUID v4 hex with dashes
        assert result.started_at.endswith("Z") or "T" in result.started_at
        assert result.pool_size == 0
        assert result.pool_puzzle_ids == []

        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?", (result.session_id,)
        ).fetchone()
        assert row is not None
        assert row["mode"] == "time"
        assert row["target"] == 5
        assert row["auto_advance"] == 1
        assert row["dedupe_solved"] == 1
        assert row["label"] == "my session"
        assert json.loads(row["filters_json"])["rating_min"] == 1500
        assert row["ended_at"] is None
        assert row["parent_session"] is None
    finally:
        conn.close()
