from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone

from app.models import CreateSessionRequest, CreateSessionResponse


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
