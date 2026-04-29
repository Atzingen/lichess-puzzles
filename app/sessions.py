from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from app.models import (
    AppendAttemptRequest,
    AttemptDetail,
    CreateSessionRequest,
    CreateSessionResponse,
    EndSessionRequest,
    EndSessionResponse,
    SessionDetail,
    SessionListItem,
    SessionSummary,
    SessionWithAttempts,
)


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


def end_session(
    conn: sqlite3.Connection, session_id: str, req: EndSessionRequest
) -> EndSessionResponse:
    ended_at = _get_session_ended_at(conn, session_id)
    if ended_at is not None:
        raise SessionEnded(session_id)
    new_ended_at = _now_iso()
    conn.execute(
        "UPDATE sessions SET ended_at = ?, end_reason = ? WHERE session_id = ?",
        (new_ended_at, req.end_reason, session_id),
    )
    summary_row = conn.execute(
        """
        SELECT COUNT(*) AS total,
               COALESCE(SUM(correct), 0) AS correct,
               COALESCE(SUM(time_ms), 0) AS total_time_ms
        FROM attempts WHERE session_id = ?
        """,
        (session_id,),
    ).fetchone()
    conn.commit()
    return EndSessionResponse(
        ended_at=new_ended_at,
        summary=SessionSummary(
            total=summary_row["total"],
            correct=summary_row["correct"],
            total_time_ms=summary_row["total_time_ms"],
        ),
    )


def list_sessions(
    conn: sqlite3.Connection, limit: int = 20, offset: int = 0
) -> list[SessionListItem]:
    rows = conn.execute(
        """
        SELECT s.session_id, s.started_at, s.ended_at, s.mode, s.target, s.label,
               COALESCE(a.total, 0)   AS total,
               COALESCE(a.correct, 0) AS correct
        FROM sessions s
        LEFT JOIN (
            SELECT session_id,
                   COUNT(*) AS total,
                   SUM(correct) AS correct
            FROM attempts GROUP BY session_id
        ) a ON a.session_id = s.session_id
        ORDER BY s.started_at DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    ).fetchall()
    return [
        SessionListItem(
            session_id=r["session_id"],
            started_at=r["started_at"],
            ended_at=r["ended_at"],
            mode=r["mode"],
            target=r["target"],
            total=r["total"],
            correct=r["correct"],
            label=r["label"],
        )
        for r in rows
    ]


def get_session_with_attempts(
    conn: sqlite3.Connection, session_id: str
) -> SessionWithAttempts:
    s = conn.execute(
        "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
    ).fetchone()
    if s is None:
        raise SessionNotFound(session_id)
    rows = conn.execute(
        """
        SELECT a.order_idx, a.puzzle_id, a.correct, a.time_ms, a.completed_at,
               p.rating, p.themes
        FROM attempts a
        LEFT JOIN puzzles p ON p.puzzle_id = a.puzzle_id
        WHERE a.session_id = ?
        ORDER BY a.order_idx ASC
        """,
        (session_id,),
    ).fetchall()
    attempts = [
        AttemptDetail(
            order_idx=r["order_idx"],
            puzzle_id=r["puzzle_id"],
            correct=bool(r["correct"]),
            time_ms=r["time_ms"],
            completed_at=r["completed_at"],
            rating=r["rating"] or 0,
            themes=(r["themes"] or "").split() if r["themes"] else [],
        )
        for r in rows
    ]
    detail = SessionDetail(
        session_id=s["session_id"],
        started_at=s["started_at"],
        ended_at=s["ended_at"],
        end_reason=s["end_reason"],
        mode=s["mode"],
        target=s["target"],
        auto_advance=bool(s["auto_advance"]),
        dedupe_solved=bool(s["dedupe_solved"]),
        filters=json.loads(s["filters_json"]),
        parent_session=s["parent_session"],
        label=s["label"],
    )
    return SessionWithAttempts(session=detail, attempts=attempts)
