# Session Trainer — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the persistent skeleton + routing for the session trainer described in `docs/superpowers/specs/2026-04-29-session-trainer-design.md`. After this phase, the app exposes session lifecycle endpoints (create/end/list/get/attempts) backed by two new SQLite tables, the current single-page UI is preserved at `/explore`, and `/` shows a minimal config stub that lists previous sessions. No actual trainer gameplay yet — that is Phase 2.

**Architecture:** Two new SQLite tables (`sessions`, `attempts`) added additively to the existing `puzzles.sqlite` via `CREATE IF NOT EXISTS`. A new `app/sessions.py` module holds the SQL business logic (mirroring `app/queries.py`). A new `app/routers/sessions.py` registers five endpoints. `app/main.py` gains a route for `/explore` that serves the old single-page HTML. Frontend split: `static/index.html` becomes the new config stub, `static/explore.html` is the renamed old page; `static/js/main.js` becomes `static/js/explore.js`, and a new `static/js/config.js` is added for the stub.

**Tech Stack:** Python 3.12, FastAPI, SQLite (stdlib `sqlite3`), Pydantic v2, pytest + httpx via `fastapi.testclient.TestClient`, vanilla HTML/JS (no bundler).

**Working directory:** `/home/gustavo/Desktop/dev/lichess-puzzles`

**Success criteria:**
- All new pytest tests pass; existing tests still pass.
- `curl -X POST http://localhost:8000/api/sessions -d '{...}'` creates a row, `curl -X POST .../attempts` records, `GET /api/sessions` lists, `GET /api/sessions/{id}` returns row + attempts joined with `puzzles`.
- `GET /` returns the new stub (lists past sessions); `GET /explore` returns the old single-page UI unchanged.
- Spec section 4 (data model) and section 5 (API) are fully covered.

---

## Task 1: Add `sessions` and `attempts` tables to schema

**Files:**
- Modify: `app/db.py`
- Modify: `tests/test_db.py`

- [ ] **Step 1: Write failing tests for new tables and indexes**

Replace the body of `tests/test_db.py:test_init_db_creates_tables_and_indexes` with the version below (extends the existing assertions; do not delete the puzzle-table assertions):

```python
def test_init_db_creates_tables_and_indexes(tmp_path: Path) -> None:
    db_path = tmp_path / "t.sqlite"
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        indexes = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
        )}
    finally:
        conn.close()

    assert "puzzles" in tables
    assert "puzzle_themes" in tables
    assert "sessions" in tables
    assert "attempts" in tables
    for needed in [
        "idx_rating", "idx_piece_count", "idx_move_number",
        "idx_phase", "idx_side", "idx_popularity", "idx_theme",
        "idx_sessions_started", "idx_attempts_session", "idx_attempts_puzzle",
    ]:
        assert needed in indexes, f"missing index {needed}"
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `pytest tests/test_db.py::test_init_db_creates_tables_and_indexes -v`
Expected: FAIL — `AssertionError: assert 'sessions' in tables` (or similar).

- [ ] **Step 3: Add the schema in `app/db.py`**

In `app/db.py`, append to the `SCHEMA` constant the two new `CREATE TABLE` statements, and append three entries to `INDEXES`. Final state of these two constants:

```python
SCHEMA = """
CREATE TABLE IF NOT EXISTS puzzles (
    puzzle_id          TEXT PRIMARY KEY,
    fen                TEXT NOT NULL,
    moves              TEXT NOT NULL,
    rating             INTEGER NOT NULL,
    rating_deviation   INTEGER NOT NULL,
    popularity         INTEGER NOT NULL,
    nb_plays           INTEGER NOT NULL,
    themes             TEXT NOT NULL,
    game_url           TEXT,
    opening_tags       TEXT,
    piece_count        INTEGER NOT NULL,
    move_number        INTEGER NOT NULL,
    side_to_move       TEXT NOT NULL,
    phase              TEXT NOT NULL,
    material_balance   INTEGER NOT NULL,
    has_promoted       INTEGER NOT NULL,
    has_en_passant     INTEGER NOT NULL,
    castling_rights    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS puzzle_themes (
    puzzle_id  TEXT NOT NULL,
    theme      TEXT NOT NULL,
    PRIMARY KEY (puzzle_id, theme)
);

CREATE TABLE IF NOT EXISTS sessions (
    session_id      TEXT PRIMARY KEY,
    started_at      TEXT NOT NULL,
    ended_at        TEXT,
    end_reason      TEXT,
    mode            TEXT NOT NULL,
    target          INTEGER,
    auto_advance    INTEGER NOT NULL,
    dedupe_solved   INTEGER NOT NULL,
    filters_json    TEXT NOT NULL,
    parent_session  TEXT,
    label           TEXT
);

CREATE TABLE IF NOT EXISTS attempts (
    session_id      TEXT NOT NULL,
    order_idx       INTEGER NOT NULL,
    puzzle_id       TEXT NOT NULL,
    correct         INTEGER NOT NULL,
    time_ms         INTEGER NOT NULL,
    completed_at    TEXT NOT NULL,
    PRIMARY KEY (session_id, order_idx),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_rating        ON puzzles(rating)",
    "CREATE INDEX IF NOT EXISTS idx_piece_count   ON puzzles(piece_count)",
    "CREATE INDEX IF NOT EXISTS idx_move_number   ON puzzles(move_number)",
    "CREATE INDEX IF NOT EXISTS idx_phase         ON puzzles(phase)",
    "CREATE INDEX IF NOT EXISTS idx_side          ON puzzles(side_to_move)",
    "CREATE INDEX IF NOT EXISTS idx_popularity    ON puzzles(popularity)",
    "CREATE INDEX IF NOT EXISTS idx_theme         ON puzzle_themes(theme)",
    "CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_attempts_session ON attempts(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_attempts_puzzle  ON attempts(puzzle_id)",
]
```

`dedupe_solved` is included now even though Phase 1 doesn't use it — it lives in the schema from day one to avoid a future migration when Phase 2 starts honoring it.

- [ ] **Step 4: Run the test and verify it passes**

Run: `pytest tests/test_db.py -v`
Expected: PASS (both `test_init_db_creates_tables_and_indexes` and `test_connect_returns_row_factory`).

- [ ] **Step 5: Commit**

```bash
git add app/db.py tests/test_db.py
git commit -m "$(cat <<'EOF'
feat(db): add sessions and attempts tables

Additive CREATE IF NOT EXISTS — old DBs upgrade on next app boot
without manual migration. Indexes match the spec section 4.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Pydantic models for session lifecycle

**Files:**
- Modify: `app/models.py`
- Test: implicit (models are exercised by the router tests in later tasks)

- [ ] **Step 1: Append the new models to `app/models.py`**

Add at the end of `app/models.py`:

```python
class CreateSessionRequest(BaseModel):
    mode: Literal["time", "count", "free"]
    target: int | None = None
    auto_advance: bool = True
    dedupe_solved: bool = True
    filters: Filters = Field(default_factory=Filters)
    parent_session: str | None = None
    label: str | None = None


class CreateSessionResponse(BaseModel):
    session_id: str
    started_at: str
    pool_size: int = 0
    pool_puzzle_ids: list[str] = Field(default_factory=list)


class AppendAttemptRequest(BaseModel):
    order_idx: int
    puzzle_id: str
    correct: bool
    time_ms: int


class EndSessionRequest(BaseModel):
    end_reason: Literal["time", "count", "manual"]


class SessionSummary(BaseModel):
    total: int
    correct: int
    total_time_ms: int


class EndSessionResponse(BaseModel):
    ended_at: str
    summary: SessionSummary


class SessionListItem(BaseModel):
    session_id: str
    started_at: str
    ended_at: str | None
    mode: str
    target: int | None
    total: int
    correct: int
    label: str | None


class AttemptDetail(BaseModel):
    order_idx: int
    puzzle_id: str
    correct: bool
    time_ms: int
    completed_at: str
    rating: int
    themes: list[str]


class SessionDetail(BaseModel):
    session_id: str
    started_at: str
    ended_at: str | None
    end_reason: str | None
    mode: str
    target: int | None
    auto_advance: bool
    dedupe_solved: bool
    filters: dict
    parent_session: str | None
    label: str | None


class SessionWithAttempts(BaseModel):
    session: SessionDetail
    attempts: list[AttemptDetail]
```

- [ ] **Step 2: Smoke-import to verify Pydantic accepts the definitions**

Run: `python -c "from app.models import CreateSessionRequest, CreateSessionResponse, AppendAttemptRequest, EndSessionRequest, EndSessionResponse, SessionListItem, AttemptDetail, SessionDetail, SessionWithAttempts; print('ok')"`
Expected: `ok` printed; no exceptions.

- [ ] **Step 3: Run the existing test suite to confirm nothing broke**

Run: `pytest -v`
Expected: all existing tests still pass.

- [ ] **Step 4: Commit**

```bash
git add app/models.py
git commit -m "$(cat <<'EOF'
feat(models): add session lifecycle Pydantic schemas

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: `app/sessions.py` — `create_session` (without `parent_session`)

**Files:**
- Create: `app/sessions.py`
- Create: `tests/test_sessions.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_sessions.py`:

```python
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
```

- [ ] **Step 2: Run and verify it fails**

Run: `pytest tests/test_sessions.py::test_create_session_returns_uuid_and_inserts_row -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.sessions'`.

- [ ] **Step 3: Implement `app/sessions.py`**

Create `app/sessions.py`:

```python
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
```

- [ ] **Step 4: Run and verify it passes**

Run: `pytest tests/test_sessions.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/sessions.py tests/test_sessions.py
git commit -m "$(cat <<'EOF'
feat(sessions): create_session writes a row and returns UUID

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: `POST /api/sessions` endpoint

**Files:**
- Create: `app/routers/sessions.py`
- Modify: `app/main.py`
- Modify: `tests/test_sessions.py` (append)

- [ ] **Step 1: Write failing test**

Append to `tests/test_sessions.py`:

```python
from fastapi.testclient import TestClient


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
```

- [ ] **Step 2: Run and verify it fails**

Run: `pytest tests/test_sessions.py::test_post_sessions_creates_session -v`
Expected: FAIL — 404 Not Found (route doesn't exist yet).

- [ ] **Step 3: Implement the router**

Create `app/routers/sessions.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.config import settings
from app.db import connect
from app.models import CreateSessionRequest, CreateSessionResponse
from app.sessions import create_session

router = APIRouter(prefix="/api/sessions")


def _conn():
    conn = connect(settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


@router.post("", response_model=CreateSessionResponse, status_code=201)
def post_session(req: CreateSessionRequest, conn=Depends(_conn)) -> CreateSessionResponse:
    return create_session(conn, req)
```

- [ ] **Step 4: Register the router in `app/main.py`**

In `app/main.py`, add the import and `include_router` call so the file's relevant section becomes:

```python
from app.routers import meta as meta_router
from app.routers import puzzles as puzzles_router
from app.routers import sessions as sessions_router

# ... existing code ...

app = FastAPI(title="lichess-puzzles", version="0.1.0")
app.include_router(meta_router.router)
app.include_router(puzzles_router.router)
app.include_router(sessions_router.router)
```

- [ ] **Step 5: Run and verify it passes**

Run: `pytest tests/test_sessions.py -v`
Expected: both new tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/routers/sessions.py app/main.py tests/test_sessions.py
git commit -m "$(cat <<'EOF'
feat(sessions): POST /api/sessions endpoint

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: `append_attempt` + `POST /api/sessions/{id}/attempts` (idempotent)

**Files:**
- Modify: `app/sessions.py`
- Modify: `app/routers/sessions.py`
- Modify: `tests/test_sessions.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_sessions.py`:

```python
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
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_sessions.py::test_post_attempt_records_row -v`
Expected: FAIL with 404 (route not yet defined).

- [ ] **Step 3: Implement `append_attempt` in `app/sessions.py`**

Append to `app/sessions.py`:

```python
from app.models import AppendAttemptRequest


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
```

- [ ] **Step 4: Wire the route in `app/routers/sessions.py`**

Append to `app/routers/sessions.py`:

```python
from fastapi import Response

from app.models import AppendAttemptRequest
from app.sessions import SessionEnded, SessionNotFound, append_attempt


@router.post("/{session_id}/attempts", status_code=204)
def post_attempt(
    session_id: str, req: AppendAttemptRequest, conn=Depends(_conn)
) -> Response:
    try:
        append_attempt(conn, session_id, req)
    except SessionNotFound:
        raise HTTPException(404, "session not found")
    except SessionEnded:
        raise HTTPException(409, "session has ended")
    return Response(status_code=204)
```

- [ ] **Step 5: Run all session tests**

Run: `pytest tests/test_sessions.py -v`
Expected: all four `test_post_attempt_*` and earlier tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/sessions.py app/routers/sessions.py tests/test_sessions.py
git commit -m "$(cat <<'EOF'
feat(sessions): POST /api/sessions/{id}/attempts (idempotent)

ON CONFLICT(session_id, order_idx) DO UPDATE so client retries are safe.
404 if session missing; 409 if session has ended.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: `end_session` + `POST /api/sessions/{id}/end`

**Files:**
- Modify: `app/sessions.py`
- Modify: `app/routers/sessions.py`
- Modify: `tests/test_sessions.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_sessions.py`:

```python
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
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_sessions.py::test_post_end_sets_ended_at_and_returns_summary -v`
Expected: FAIL with 404 / 405 (endpoint doesn't exist).

- [ ] **Step 3: Implement `end_session`**

Append to `app/sessions.py`:

```python
from app.models import EndSessionRequest, EndSessionResponse, SessionSummary


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
```

- [ ] **Step 4: Wire the route**

Append to `app/routers/sessions.py`:

```python
from app.models import EndSessionRequest, EndSessionResponse
from app.sessions import end_session


@router.post("/{session_id}/end", response_model=EndSessionResponse)
def post_end(
    session_id: str, req: EndSessionRequest, conn=Depends(_conn)
) -> EndSessionResponse:
    try:
        return end_session(conn, session_id, req)
    except SessionNotFound:
        raise HTTPException(404, "session not found")
    except SessionEnded:
        raise HTTPException(409, "session already ended")
```

- [ ] **Step 5: Run and verify**

Run: `pytest tests/test_sessions.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add app/sessions.py app/routers/sessions.py tests/test_sessions.py
git commit -m "$(cat <<'EOF'
feat(sessions): POST /api/sessions/{id}/end with summary

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: `list_sessions` + `GET /api/sessions`

**Files:**
- Modify: `app/sessions.py`
- Modify: `app/routers/sessions.py`
- Modify: `tests/test_sessions.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_sessions.py`:

```python
def test_get_sessions_lists_in_reverse_chrono(app_with_db) -> None:
    c = TestClient(app_with_db)
    sid_a = c.post("/api/sessions", json={
        "mode": "count", "target": 1, "filters": {}, "label": "A"
    }).json()["session_id"]
    c.post(f"/api/sessions/{sid_a}/attempts", json={
        "order_idx": 0, "puzzle_id": "00008", "correct": True, "time_ms": 100,
    })
    c.post(f"/api/sessions/{sid_a}/end", json={"end_reason": "count"})

    sid_b = c.post("/api/sessions", json={
        "mode": "time", "target": 5, "filters": {}, "label": "B"
    }).json()["session_id"]

    r = c.get("/api/sessions")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    # B was created last -> first
    assert body[0]["session_id"] == sid_b
    assert body[0]["label"] == "B"
    assert body[0]["ended_at"] is None
    assert body[0]["total"] == 0
    assert body[0]["correct"] == 0

    assert body[1]["session_id"] == sid_a
    assert body[1]["total"] == 1
    assert body[1]["correct"] == 1
    assert body[1]["ended_at"] is not None


def test_get_sessions_respects_limit_offset(app_with_db) -> None:
    c = TestClient(app_with_db)
    for i in range(3):
        c.post("/api/sessions", json={
            "mode": "count", "target": 1, "filters": {}, "label": f"S{i}"
        })
    r = c.get("/api/sessions", params={"limit": 2, "offset": 1})
    assert r.status_code == 200
    assert len(r.json()) == 2
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_sessions.py::test_get_sessions_lists_in_reverse_chrono -v`
Expected: FAIL with 404.

- [ ] **Step 3: Implement `list_sessions`**

Append to `app/sessions.py`:

```python
from app.models import SessionListItem


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
```

- [ ] **Step 4: Wire the route**

Append to `app/routers/sessions.py`:

```python
from app.models import SessionListItem
from app.sessions import list_sessions


@router.get("", response_model=list[SessionListItem])
def get_sessions(
    limit: int = 20, offset: int = 0, conn=Depends(_conn)
) -> list[SessionListItem]:
    return list_sessions(conn, limit=limit, offset=offset)
```

- [ ] **Step 5: Run and verify**

Run: `pytest tests/test_sessions.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add app/sessions.py app/routers/sessions.py tests/test_sessions.py
git commit -m "$(cat <<'EOF'
feat(sessions): GET /api/sessions list with totals

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: `get_session_with_attempts` + `GET /api/sessions/{id}`

**Files:**
- Modify: `app/sessions.py`
- Modify: `app/routers/sessions.py`
- Modify: `tests/test_sessions.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_sessions.py`:

```python
def test_get_session_returns_session_and_joined_attempts(app_with_db) -> None:
    c = TestClient(app_with_db)
    sid = c.post("/api/sessions", json={
        "mode": "count", "target": 2, "filters": {"rating_min": 1500},
    }).json()["session_id"]
    c.post(f"/api/sessions/{sid}/attempts", json={
        "order_idx": 0, "puzzle_id": "00008", "correct": True, "time_ms": 1200,
    })
    c.post(f"/api/sessions/{sid}/attempts", json={
        "order_idx": 1, "puzzle_id": "0000D", "correct": False, "time_ms": 5400,
    })

    r = c.get(f"/api/sessions/{sid}")
    assert r.status_code == 200
    body = r.json()
    assert body["session"]["session_id"] == sid
    assert body["session"]["mode"] == "count"
    assert body["session"]["filters"]["rating_min"] == 1500
    assert len(body["attempts"]) == 2
    a0 = body["attempts"][0]
    assert a0["puzzle_id"] == "00008"
    assert a0["rating"] == 1812          # joined from puzzles
    assert "advantage" in a0["themes"]


def test_get_session_404(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/api/sessions/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_sessions.py::test_get_session_returns_session_and_joined_attempts -v`
Expected: FAIL with 404 (route undefined; FastAPI returns "Method Not Allowed" or similar).

- [ ] **Step 3: Implement**

Append to `app/sessions.py`:

```python
import json as _json

from app.models import AttemptDetail, SessionDetail, SessionWithAttempts


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
        filters=_json.loads(s["filters_json"]),
        parent_session=s["parent_session"],
        label=s["label"],
    )
    return SessionWithAttempts(session=detail, attempts=attempts)
```

- [ ] **Step 4: Wire the route**

Append to `app/routers/sessions.py`:

```python
from app.models import SessionWithAttempts
from app.sessions import get_session_with_attempts


@router.get("/{session_id}", response_model=SessionWithAttempts)
def get_session(session_id: str, conn=Depends(_conn)) -> SessionWithAttempts:
    try:
        return get_session_with_attempts(conn, session_id)
    except SessionNotFound:
        raise HTTPException(404, "session not found")
```

- [ ] **Step 5: Run and verify**

Run: `pytest tests/test_sessions.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add app/sessions.py app/routers/sessions.py tests/test_sessions.py
git commit -m "$(cat <<'EOF'
feat(sessions): GET /api/sessions/{id} with joined attempts

JOIN puzzles to bring rating + themes for the stats screen and the
end-of-session "redo failed" flow.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: `parent_session` support in `create_session`

**Files:**
- Modify: `app/sessions.py`
- Modify: `tests/test_sessions.py`

This task makes `parent_session` populate `pool_size` and `pool_puzzle_ids` in the create response by reading the parent's failed attempts.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_sessions.py`:

```python
def test_create_session_with_parent_returns_failed_puzzles(app_with_db) -> None:
    c = TestClient(app_with_db)
    parent = c.post("/api/sessions", json={
        "mode": "count", "target": 3, "filters": {}
    }).json()["session_id"]
    c.post(f"/api/sessions/{parent}/attempts", json={
        "order_idx": 0, "puzzle_id": "00008", "correct": True, "time_ms": 100,
    })
    c.post(f"/api/sessions/{parent}/attempts", json={
        "order_idx": 1, "puzzle_id": "0000D", "correct": False, "time_ms": 200,
    })
    c.post(f"/api/sessions/{parent}/attempts", json={
        "order_idx": 2, "puzzle_id": "0008Q", "correct": False, "time_ms": 300,
    })
    c.post(f"/api/sessions/{parent}/end", json={"end_reason": "count"})

    r = c.post("/api/sessions", json={
        "mode": "count", "target": 2,
        "filters": {}, "parent_session": parent,
    })
    assert r.status_code == 201
    body = r.json()
    assert body["pool_size"] == 2
    assert sorted(body["pool_puzzle_ids"]) == ["0000D", "0008Q"]


def test_create_session_404_on_missing_parent(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.post("/api/sessions", json={
        "mode": "count", "target": 1, "filters": {},
        "parent_session": "00000000-0000-0000-0000-000000000000",
    })
    assert r.status_code == 404
```

- [ ] **Step 2: Run and verify failure**

Run: `pytest tests/test_sessions.py::test_create_session_with_parent_returns_failed_puzzles -v`
Expected: FAIL — `pool_size` is 0 because parent is currently ignored.

- [ ] **Step 3: Update `create_session` to handle `parent_session`**

In `app/sessions.py`, replace the body of `create_session` with:

```python
def create_session(
    conn: sqlite3.Connection, req: CreateSessionRequest
) -> CreateSessionResponse:
    pool_ids: list[str] = []
    if req.parent_session is not None:
        parent = conn.execute(
            "SELECT 1 FROM sessions WHERE session_id = ?", (req.parent_session,)
        ).fetchone()
        if parent is None:
            raise SessionNotFound(req.parent_session)
        rows = conn.execute(
            """
            SELECT puzzle_id FROM attempts
            WHERE session_id = ? AND correct = 0
            ORDER BY order_idx ASC
            """,
            (req.parent_session,),
        ).fetchall()
        pool_ids = [r["puzzle_id"] for r in rows]

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
        pool_size=len(pool_ids),
        pool_puzzle_ids=pool_ids,
    )
```

- [ ] **Step 4: Map `SessionNotFound` to HTTP 404 in the create route**

In `app/routers/sessions.py`, replace the body of `post_session` with:

```python
@router.post("", response_model=CreateSessionResponse, status_code=201)
def post_session(req: CreateSessionRequest, conn=Depends(_conn)) -> CreateSessionResponse:
    try:
        return create_session(conn, req)
    except SessionNotFound:
        raise HTTPException(404, "parent session not found")
```

- [ ] **Step 5: Run and verify**

Run: `pytest tests/test_sessions.py -v`
Expected: all PASS, including the new parent tests.

- [ ] **Step 6: Commit**

```bash
git add app/sessions.py app/routers/sessions.py tests/test_sessions.py
git commit -m "$(cat <<'EOF'
feat(sessions): parent_session populates pool from parent's failed attempts

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Move existing single-page UI from `/` to `/explore`

**Files:**
- Rename: `static/index.html` → `static/explore.html`
- Rename: `static/js/main.js` → `static/js/explore.js`
- Modify: `static/explore.html` (just the script src reference)
- Modify: `app/main.py` (add `/explore` route, keep `/` serving the maintenance HTML for now — Task 11 fills it with the real stub)
- Modify: `tests/test_main.py`

- [ ] **Step 1: Move the files**

Run:
```bash
git mv static/index.html static/explore.html
git mv static/js/main.js static/js/explore.js
```

- [ ] **Step 2: Update the script tag inside `static/explore.html`**

In `static/explore.html`, change:
```html
<script type="module" src="/static/js/main.js"></script>
```
to:
```html
<script type="module" src="/static/js/explore.js"></script>
```

- [ ] **Step 3: Update `app/main.py` to serve `/explore` and put a placeholder at `/`**

Replace the content of `app/main.py` with:

```python
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.routers import meta as meta_router
from app.routers import puzzles as puzzles_router
from app.routers import sessions as sessions_router

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
MAINTENANCE_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>lichess-puzzles — maintenance</title>
<style>body{font-family:sans-serif;max-width:640px;margin:4rem auto;padding:1rem}
code{background:#eee;padding:.1rem .3rem;border-radius:.2rem}</style></head>
<body>
<h1>Banco ainda n&atilde;o populado</h1>
<p>O arquivo SQLite n&atilde;o existe. Rode <code>make ingest</code> para
baixar e importar o dump oficial do Lichess (~5-10 min).</p>
</body></html>
"""

# Phase-1 placeholder for `/`; Task 11 swaps this for a real stub file.
ROOT_PLACEHOLDER_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>lichess-puzzles</title></head>
<body><h1>lichess-puzzles</h1>
<p>Configuração da sessão (Fase 2 ativará).</p>
<p><a href="/explore">/explore</a></p></body></html>
"""


def _db_exists() -> bool:
    return settings.db_path.exists()


app = FastAPI(title="lichess-puzzles", version="0.1.0")
app.include_router(meta_router.router)
app.include_router(puzzles_router.router)
app.include_router(sessions_router.router)


@app.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:
    if not _db_exists():
        return HTMLResponse(MAINTENANCE_HTML)
    return HTMLResponse(ROOT_PLACEHOLDER_HTML)


@app.get("/explore", response_class=HTMLResponse)
def explore() -> HTMLResponse:
    if not _db_exists():
        return HTMLResponse(MAINTENANCE_HTML)
    return HTMLResponse((STATIC_DIR / "explore.html").read_text(encoding="utf-8"))


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True, "db": _db_exists()}


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
```

- [ ] **Step 4: Update `tests/test_main.py` to reflect the new routes**

Replace `tests/test_main.py` with:

```python
from fastapi.testclient import TestClient


def test_root_serves_phase1_stub_when_db_exists(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/")
    assert r.status_code == 200
    assert "configuração" in r.text.lower() or "configuracao" in r.text.lower() or "<h1>" in r.text


def test_explore_serves_old_single_page(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/explore")
    assert r.status_code == 200
    assert "chessground" in r.text.lower()
    assert "/static/js/explore.js" in r.text


def test_health_ok(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "db": True}


def test_health_reports_missing_db(app_without_db) -> None:
    c = TestClient(app_without_db)
    r = c.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "db": False}


def test_root_shows_maintenance_page_when_db_missing(app_without_db) -> None:
    c = TestClient(app_without_db)
    r = c.get("/")
    assert r.status_code == 200
    assert "ingest" in r.text.lower()


def test_explore_shows_maintenance_page_when_db_missing(app_without_db) -> None:
    c = TestClient(app_without_db)
    r = c.get("/explore")
    assert r.status_code == 200
    assert "ingest" in r.text.lower()
```

- [ ] **Step 5: Run the full test suite**

Run: `pytest -v`
Expected: all tests PASS (including the existing puzzle/meta/db ones, plus the new session ones, plus the rewritten main tests).

- [ ] **Step 6: Smoke-check that `/explore` actually loads in a browser**

Run (in a separate terminal): `uvicorn app.main:app --reload`
Then: `curl -s http://127.0.0.1:8000/explore | head -20`
Expected: HTML output showing the chessground import map and `/static/js/explore.js`.

Stop the server (`Ctrl+C`).

- [ ] **Step 7: Commit**

```bash
git add static/ app/main.py tests/test_main.py
git commit -m "$(cat <<'EOF'
refactor(routing): move single-page UI to /explore, stub root

The current single-page filter+board+info UI is preserved verbatim at
/explore. Root serves a Phase-1 placeholder; Task 11 fills it in.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Stub the new `/` with a sessions-list page

**Files:**
- Create: `static/index.html` (new)
- Create: `static/js/config.js`
- Create: `static/css/config.css`
- Modify: `app/main.py` (root now serves the file instead of the inline HTML constant)
- Modify: `tests/test_main.py`

- [ ] **Step 1: Write the new `static/index.html`**

Create `static/index.html`:

```html
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>lichess-puzzles — sessão</title>
<link rel="stylesheet" href="/static/css/styles.css"/>
<link rel="stylesheet" href="/static/css/config.css"/>
</head>
<body>
<header>
  <h1>lichess-puzzles</h1>
  <nav><a href="/explore">/explore</a></nav>
</header>

<main class="config-main">
  <section class="panel" id="phase1-note">
    <p><strong>Fase 1.</strong> O treinador de sessão será conectado na Fase 2.
    Por enquanto, esta página apenas lista as sessões já registradas no banco.</p>
  </section>

  <section class="panel">
    <h2>Sessões anteriores</h2>
    <ul id="sessions-list"><li class="empty">Carregando…</li></ul>
  </section>
</main>

<script type="module" src="/static/js/config.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `static/css/config.css`**

Create `static/css/config.css`:

```css
.config-main {
  max-width: 960px;
  margin: 1rem auto;
  padding: 0 1rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
header nav a {
  color: var(--accent);
  text-decoration: none;
  margin-left: 1rem;
}
#sessions-list {
  list-style: none;
  padding: 0;
  margin: 0;
}
#sessions-list li {
  display: flex;
  gap: 1rem;
  padding: .4rem 0;
  border-bottom: 1px solid var(--border);
  font-family: ui-monospace, monospace;
  font-size: .9rem;
}
#sessions-list li.empty {
  font-family: inherit;
  font-style: italic;
  color: #999;
  border: 0;
}
#sessions-list .label { flex: 1; }
#sessions-list .target { width: 7rem; }
#sessions-list .score  { width: 5rem; text-align: right; }
```

- [ ] **Step 3: Write `static/js/config.js`**

Create `static/js/config.js`:

```javascript
async function loadSessions() {
  const ul = document.getElementById('sessions-list');
  try {
    const r = await fetch('/api/sessions?limit=20');
    if (!r.ok) throw new Error('http ' + r.status);
    const list = await r.json();
    if (list.length === 0) {
      ul.innerHTML = '<li class="empty">Nenhuma sessão ainda.</li>';
      return;
    }
    ul.innerHTML = '';
    for (const s of list) {
      const li = document.createElement('li');
      const when = formatStarted(s.started_at);
      const target = formatTarget(s.mode, s.target);
      const score = `${s.correct}/${s.total}`;
      li.innerHTML = `
        <span class="when">${when}</span>
        <span class="target">${target}</span>
        <span class="label">${escapeHtml(s.label || '')}</span>
        <span class="score">${score}</span>
      `;
      ul.append(li);
    }
  } catch (e) {
    ul.innerHTML = `<li class="empty">Erro ao carregar: ${e.message}</li>`;
  }
}

function formatStarted(iso) {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
}

function formatTarget(mode, target) {
  if (mode === 'free') return 'livre';
  if (mode === 'time') return `${target} min`;
  if (mode === 'count') return `${target} puzzles`;
  return mode;
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[ch]));
}

loadSessions();
```

- [ ] **Step 4: Update `app/main.py` to serve the file**

In `app/main.py`, delete the `ROOT_PLACEHOLDER_HTML` constant and replace the `root()` function:

```python
@app.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:
    if not _db_exists():
        return HTMLResponse(MAINTENANCE_HTML)
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))
```

- [ ] **Step 5: Update `tests/test_main.py`**

Replace `test_root_serves_phase1_stub_when_db_exists` in `tests/test_main.py` with:

```python
def test_root_serves_config_stub(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/")
    assert r.status_code == 200
    assert "/static/js/config.js" in r.text
    assert "Sessões anteriores" in r.text
```

- [ ] **Step 6: Run all tests**

Run: `pytest -v`
Expected: all PASS.

- [ ] **Step 7: Manual smoke (browser)**

Run: `uvicorn app.main:app --reload`
Open `http://127.0.0.1:8000/` — expect to see the header, the Phase-1 note, and "Nenhuma sessão ainda." or a list (depending on local DB state).
Open `http://127.0.0.1:8000/explore` — expect the original single-page UI with filters + board.

Then create one fake session via curl and reload `/`:

```bash
SID=$(curl -s -X POST http://127.0.0.1:8000/api/sessions \
  -H 'Content-Type: application/json' \
  -d '{"mode":"count","target":1,"filters":{},"label":"smoke test"}' | jq -r .session_id)
curl -s -X POST http://127.0.0.1:8000/api/sessions/$SID/attempts \
  -H 'Content-Type: application/json' \
  -d '{"order_idx":0,"puzzle_id":"00008","correct":true,"time_ms":1234}'
curl -s -X POST http://127.0.0.1:8000/api/sessions/$SID/end \
  -H 'Content-Type: application/json' \
  -d '{"end_reason":"manual"}' | jq .
```

Reload `/` in the browser — the sessions list should now show the fake session.

Stop the server.

- [ ] **Step 8: Commit**

```bash
git add static/index.html static/css/config.css static/js/config.js app/main.py tests/test_main.py
git commit -m "$(cat <<'EOF'
feat(frontend): config-screen stub at / listing past sessions

Phase 1 lands a minimal placeholder page that fetches GET /api/sessions
and renders the list. Phase 2 will turn this into the real config UI.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: End-to-end verification and PR-ready summary

**Files:** none — verification only.

- [ ] **Step 1: Run the entire test suite**

Run: `pytest -v`
Expected: all tests PASS, including all `tests/test_sessions.py` (12 tests), the rewritten `tests/test_main.py` (6 tests), and every previously existing test.

- [ ] **Step 2: Confirm both routes load against a real ingested DB**

If `data/puzzles.sqlite` already exists locally, run `uvicorn app.main:app --reload` and `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/`. Expect `200`. Same for `/explore`.

If the DB does not exist, run the maintenance check: `curl -s http://127.0.0.1:8000/ | grep -i ingest` should produce a hit (the maintenance HTML).

- [ ] **Step 3: Inspect the final session schema in SQLite**

Run (against a populated DB):
```bash
sqlite3 data/puzzles.sqlite ".schema sessions"
sqlite3 data/puzzles.sqlite ".schema attempts"
```
Expected: matches the schema in section 4 of the spec — no extra columns, no missing columns.

- [ ] **Step 4: Push the branch and open a PR**

Run:
```bash
git status
git log --oneline -20
```
Confirm a clean working tree and 11 commits (one per task that produced commits). Then push:
```bash
git push -u origin main
```
(There is no separate feature branch in this project's flow — `main` is the working branch, with GitHub Actions handling deploy on push as documented in the prior plan.)

The deploy job will SSH into `hostinger-02` and run `make rebuild`. After it completes, hit `http://72.61.43.231:8004/` and `http://72.61.43.231:8004/explore` to confirm both routes work in production.

---

## Files touched (summary)

```
app/db.py                          modified  (new schema)
app/models.py                      modified  (session models)
app/sessions.py                    new       (DB business logic)
app/routers/sessions.py            new       (HTTP routes)
app/main.py                        modified  (new /explore route, root serves file)
tests/test_db.py                   modified  (assert new tables/indexes)
tests/test_sessions.py             new       (12 tests)
tests/test_main.py                 modified  (rewritten for new routing)
static/index.html                  new       (config stub)
static/explore.html                renamed   (was static/index.html)
static/js/explore.js               renamed   (was static/js/main.js)
static/js/config.js                new
static/css/config.css              new
docs/superpowers/plans/2026-04-29-session-trainer-phase1.md   new (this file)
```

## What this phase does NOT deliver

These are explicitly out of scope here, and will be tackled in subsequent phase plans:

- `GET /api/puzzles/batch` (Phase 2).
- The real configuration UI on `/` with filters, knobs, "Buscar pool", "Iniciar" (Phase 2).
- The session immersive screen at `/play/:session_id` (Phase 2).
- The stats screen at `/play/:session_id/stats` (Phase 3).
- Free-mode features (Phase 4).
- Sound on error, confirmation modal, a11y polish (Phase 5).
