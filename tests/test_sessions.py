from __future__ import annotations

import json
import sqlite3

from fastapi.testclient import TestClient

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


def test_post_sessions_creates_session(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.post("/api/sessions", json={
        "mode": "count",
        "target": 50,
        "auto_advance": True,
        "dedupe_solved": True,
        "filters": {"rating_min": 1500},
        "label": "test",
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert "session_id" in body
    assert body["pool_size"] == 0
    assert body["pool_puzzle_ids"] == []


def test_post_sessions_validates_mode(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.post("/api/sessions", json={
        "mode": "invalid_mode",
        "target": 5,
        "filters": {},
    })
    assert r.status_code == 422


def test_post_attempt_records_row(app_with_db) -> None:
    c = TestClient(app_with_db)
    sid = c.post("/api/sessions", json={
        "mode": "count", "target": 5, "filters": {}
    }).json()["session_id"]

    r = c.post(f"/api/sessions/{sid}/attempts", json={
        "order_idx": 0, "puzzle_id": "00008", "correct": True, "time_ms": 1234,
    })
    assert r.status_code == 204


def test_post_attempt_is_idempotent_on_same_order_idx(app_with_db) -> None:
    c = TestClient(app_with_db)
    sid = c.post("/api/sessions", json={
        "mode": "count", "target": 5, "filters": {}
    }).json()["session_id"]
    payload = {"order_idx": 0, "puzzle_id": "00008", "correct": False, "time_ms": 100}
    r1 = c.post(f"/api/sessions/{sid}/attempts", json=payload)
    payload["correct"] = True
    payload["time_ms"] = 200
    r2 = c.post(f"/api/sessions/{sid}/attempts", json=payload)
    assert r1.status_code == 204 and r2.status_code == 204

    # Second write replaced the first
    from app.db import connect
    from app.config import settings
    conn = connect(settings.db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM attempts WHERE session_id = ?", (sid,)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["correct"] == 1
        assert rows[0]["time_ms"] == 200
    finally:
        conn.close()


def test_post_attempt_404_on_missing_session(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.post("/api/sessions/00000000-0000-0000-0000-000000000000/attempts", json={
        "order_idx": 0, "puzzle_id": "00008", "correct": True, "time_ms": 1,
    })
    assert r.status_code == 404


def test_post_end_sets_ended_at_and_returns_summary(app_with_db) -> None:
    c = TestClient(app_with_db)
    sid = c.post("/api/sessions", json={
        "mode": "count", "target": 3, "filters": {}
    }).json()["session_id"]
    for i, (pid, ok, t) in enumerate([
        ("00008", True, 1500), ("0000D", False, 3000), ("00008", True, 800)
    ]):
        c.post(f"/api/sessions/{sid}/attempts", json={
            "order_idx": i, "puzzle_id": pid, "correct": ok, "time_ms": t,
        })

    r = c.post(f"/api/sessions/{sid}/end", json={"end_reason": "count"})
    assert r.status_code == 200
    body = r.json()
    assert body["ended_at"]
    assert body["summary"]["total"] == 3
    assert body["summary"]["correct"] == 2
    assert body["summary"]["total_time_ms"] == 5300


def test_post_end_409_on_already_ended(app_with_db) -> None:
    c = TestClient(app_with_db)
    sid = c.post("/api/sessions", json={
        "mode": "count", "target": 1, "filters": {}
    }).json()["session_id"]
    r1 = c.post(f"/api/sessions/{sid}/end", json={"end_reason": "manual"})
    r2 = c.post(f"/api/sessions/{sid}/end", json={"end_reason": "manual"})
    assert r1.status_code == 200
    assert r2.status_code == 409
