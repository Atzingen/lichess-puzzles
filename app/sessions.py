from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from app.models import AppendAttemptRequest, CreateSessionRequest, CreateSessionResponse


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def create_session(
    conn: sqlite3.Connection, req: CreateSessionRequest
) -> CreateSessionResponse:
    session_id = str(uuid.uuid4())
    started_at = _now_iso()
    conn.execute(
        """
        INSERT INTO sessions (
            session_id, started_at, ended_at, end_reason,
            mode, target, auto_advance, dedupe_solved,
            filters_json, parent_session, label
        ) VALUES (?, ?, NULL, NULL, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            session_id, started_at,
            req.mode, req.target,
            1 if req.auto_advance else 0,
            1 if req.dedupe_solved else 0,
            json.dumps(req.filters.model_dump(exclude_none=True)),
            req.parent_session,
            req.label,
        ),
    )
    conn.commit()
    return CreateSessionResponse(
        session_id=session_id,
        started_at=started_at,
        pool_size=0,
        pool_puzzle_ids=[],
    )


class SessionNotFound(Exception):
    pass


class SessionEnded(Exception):
    pass


def _get_session_ended_at(conn: sqlite3.Connection, session_id: str) -> str | None:
    row = conn.execute(
        "SELECT ended_at FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise SessionNotFound(session_id)
    return row["ended_at"]


def append_attempt(
    conn: sqlite3.Connection, session_id: str, req: AppendAttemptRequest
) -> None:
    ended_at = _get_session_ended_at(conn, session_id)
    if ended_at is not None:
        raise SessionEnded(session_id)
    conn.execute(
        """
        INSERT INTO attempts (
            session_id, order_idx, puzzle_id, correct, time_ms, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(session_id, order_idx) DO UPDATE SET
            puzzle_id = excluded.puzzle_id,
            correct   = excluded.correct,
            time_ms   = excluded.time_ms,
            completed_at = excluded.completed_at
        """,
        (
            session_id, req.order_idx, req.puzzle_id,
            1 if req.correct else 0, req.time_ms, _now_iso(),
        ),
    )
    conn.commit()
