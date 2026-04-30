# Session Trainer — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the immersive session trainer described in section 6 of `docs/superpowers/specs/2026-04-29-session-trainer-design.md`. After this phase, `/` shows the full configuration screen (filters + session knobs + pool warming + previous sessions), clicking *Iniciar* creates a session row and opens `/play/:session_id`, and the user can play through a delimited block of puzzles using the correct `PREVIEW → OPPONENT_MOVE → USER_TURN` state machine. Each attempt is recorded in SQLite. The session ends when the time/count target is hit or the user clicks *Encerrar agora*; on end the user is redirected to `/explore` with a placeholder banner (the real stats screen is Phase 3).

**Architecture:**
- Backend gains one new query (`random_batch`) and one new endpoint (`GET /api/puzzles/batch`) to deliver a randomly-ordered pool of puzzles up front; the existing per-puzzle `/random` endpoint stays around for `/explore`.
- A new server route `/play/{session_id}` serves a new static page `static/play.html`. The session id is part of the URL — no HTML templating; the frontend reads `location.pathname`.
- The existing `static/js/trainer.js` is left untouched and continues to power `/explore`. A new module `static/js/play.js` is written from scratch with the state machine the spec requires (`PREVIEW → OPPONENT_MOVE → USER_TURN`), fail-fast validation, mate-in-N alternative, and asynchronous attempt POSTs.
- The pool is transferred from `/` to `/play/:id` via `sessionStorage` (`pool:<session_id>` key holding the puzzle id list returned by `/batch` — or by `POST /api/sessions` when `parent_session` is set). Each puzzle is fetched on demand from `GET /api/puzzles/{id}`.
- Free mode and stats screen are deferred to Phases 3 and 4.

**Tech Stack:** Python 3.12, FastAPI, SQLite, Pydantic v2, pytest + httpx via `fastapi.testclient.TestClient`, vanilla HTML/JS (chessground via esm.sh for dev / vendored CSS in prod, chess.js for client validation, no bundler).

**Working directory:** `/home/gustavo/Desktop/dev/lichess-puzzles`

**Success criteria (mirrors spec section 12):**
- All new pytest tests pass; existing 74-test suite still passes.
- `curl 'http://localhost:8000/api/puzzles/batch?rating_min=1000&rating_max=1500&limit=10'` returns 10 distinct puzzles in random order.
- `GET /` renders the new config screen with filters, presets, session knobs, *Buscar pool*, *Iniciar sessão*, and the *Sessões anteriores* list pulling from the backend.
- Clicking *Iniciar* creates a session row, opens `/play/:id`, and the first puzzle runs through `PREVIEW → OPPONENT_MOVE → USER_TURN` in that order with orientation matching the user's side (FEN.side_to_move flipped).
- A correct user move advances `moveIndex` by 2 (user move + opponent reply) until the puzzle is solved; a wrong move flashes red, registers an attempt with `correct=0`, and auto-advances.
- A mate-in-N puzzle accepts any legal move that delivers checkmate as the final move, even if it is not the move stored in `puzzle.moves`.
- `POST /api/sessions/{id}/attempts` is called for every attempt (fire-and-forget on the client; failures are retried).
- The clock counts down in `time` mode and counts up in `count`/`free`; on target hit (`time` reaches 0 or `count` reaches `target`) the client calls `POST /api/sessions/{id}/end` and navigates to `/explore?ended=:id`.
- Clicking *Encerrar agora* (with `confirm()` accept) calls `POST /end` and navigates away.
- `/explore` continues to behave exactly as today.

---

## Files touched in this phase

**Created:**
- `app/queries.py` — gains `random_batch` (modify, not create)
- `app/models.py` — gains `BatchResponse` (modify)
- `app/routers/puzzles.py` — gains `GET /batch` (modify)
- `app/main.py` — gains `/play/{session_id}` route (modify)
- `static/play.html` — new
- `static/css/play.css` — new
- `static/js/play.js` — new
- `tests/test_queries.py` — gains tests for `random_batch` (modify)
- `tests/test_puzzles_router.py` — gains tests for `/batch` (modify)
- `tests/test_main.py` — gains tests for `/play/:id` (modify)

**Modified (frontend rewrite):**
- `static/index.html` — config stub becomes the real config screen
- `static/css/config.css` — extended for the two-column layout + knobs + pool feedback
- `static/js/config.js` — extended with knobs reading, *Buscar pool*, *Iniciar sessão*
- `static/explore.html` — gains a one-line "Sessão encerrada" banner driven by `?ended=:id`
- `static/js/explore.js` — reads the `ended` query param and renders the banner

**Untouched on purpose:**
- `static/js/trainer.js` (powers `/explore` only — Phase 2 trainer is `play.js`)
- `app/sessions.py` (already provides every endpoint Phase 2 needs)

---

## Task 1: Backend — `random_batch` query function

Returns up to N puzzles matching the filters in random order, in a single SQL round-trip. Used once per session to warm the pool.

**Files:**
- Modify: `app/queries.py`
- Modify: `tests/test_queries.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_queries.py`:

```python
def test_random_batch_respects_limit_and_filters(populated_db: Path) -> None:
    conn = connect(populated_db)
    try:
        out = random_batch(conn, Filters(rating_min=1500, rating_max=2000), limit=3)
        assert 0 < len(out) <= 3
        for p in out:
            assert 1500 <= p.rating <= 2000
        ids = [p.puzzle_id for p in out]
        assert len(ids) == len(set(ids)), "no duplicates"
    finally:
        conn.close()


def test_random_batch_caps_at_available(populated_db: Path) -> None:
    conn = connect(populated_db)
    try:
        out = random_batch(conn, Filters(), limit=10_000)
        assert len(out) <= 10
    finally:
        conn.close()


def test_random_batch_orders_randomly_across_calls(populated_db: Path) -> None:
    conn = connect(populated_db)
    try:
        seen = set()
        for _ in range(20):
            out = random_batch(conn, Filters(), limit=10)
            seen.add(tuple(p.puzzle_id for p in out))
        assert len(seen) > 1, "ORDER BY RANDOM produced the same order 20 times"
    finally:
        conn.close()
```

Add `random_batch` to the imports at the top of the file (next to `random_puzzle`, etc.).

- [ ] **Step 2: Run the test and verify it fails**

```
pytest tests/test_queries.py::test_random_batch_respects_limit_and_filters -v
```
Expected: FAIL — `ImportError: cannot import name 'random_batch' from 'app.queries'`.

- [ ] **Step 3: Implement `random_batch` in `app/queries.py`**

Add the following function below `random_puzzle`:

```python
def random_batch(
    conn: sqlite3.Connection, filters: Filters, limit: int = 500
) -> list[Puzzle]:
    if limit <= 0:
        return []
    where, params = build_where(filters)
    sql = f"SELECT * FROM puzzles {where} ORDER BY RANDOM() LIMIT ?"
    rows = conn.execute(sql, [*params, int(limit)]).fetchall()
    return [_row_to_puzzle(r) for r in rows]
```

No new imports needed.

- [ ] **Step 4: Run the tests and verify they pass**

```
pytest tests/test_queries.py -v
```
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add app/queries.py tests/test_queries.py
git commit -m "$(cat <<'EOF'
feat(queries): random_batch returns N puzzles in random order

Used to warm the per-session pool. ORDER BY RANDOM is fine here because
the call is one-shot at session start, not per-puzzle.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Backend — `BatchResponse` model + `GET /api/puzzles/batch`

Wraps `random_batch` in an HTTP endpoint that the config screen calls when the user clicks *Buscar pool*.

**Files:**
- Modify: `app/models.py`
- Modify: `app/routers/puzzles.py`
- Modify: `tests/test_puzzles_router.py`

- [ ] **Step 1: Add the response model**

Append to `app/models.py` (right after `RandomResponse`):

```python
class BatchResponse(BaseModel):
    count: int
    puzzles: list[Puzzle]
```

- [ ] **Step 2: Write the failing router test**

Append to `tests/test_puzzles_router.py`:

```python
def test_batch_returns_at_most_limit_and_filters_rating(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/api/puzzles/batch?rating_min=1500&rating_max=2000&limit=3")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == len(body["puzzles"]) <= 3
    for p in body["puzzles"]:
        assert 1500 <= p["rating"] <= 2000


def test_batch_default_limit_caps_at_available(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/api/puzzles/batch")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == len(body["puzzles"])
    assert body["count"] <= 500


def test_batch_rejects_zero_limit(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/api/puzzles/batch?limit=0")
    assert r.status_code == 422
```

- [ ] **Step 3: Run the test to verify it fails**

```
pytest tests/test_puzzles_router.py::test_batch_returns_at_most_limit_and_filters_rating -v
```
Expected: FAIL with 404 (no such endpoint yet).

- [ ] **Step 4: Implement the endpoint**

In `app/routers/puzzles.py`:

Update the import line from `app.models`:
```python
from app.models import Filters, Puzzle, SearchResponse, RandomResponse, BatchResponse
```

Update the import line from `app.queries`:
```python
from app.queries import count_puzzles, random_puzzle, random_batch, sample_ids, get_by_id
```

Add the new endpoint above `by_id`:
```python
@router.get("/batch", response_model=BatchResponse)
def batch(
    filters: Filters = Depends(_filters_from_query),
    limit: int = Query(500, gt=0, le=2000),
    conn=Depends(_conn),
) -> BatchResponse:
    puzzles = random_batch(conn, filters, limit=limit)
    return BatchResponse(count=len(puzzles), puzzles=puzzles)
```

`/batch` must be declared before `/{puzzle_id}` in the file so FastAPI does not interpret "batch" as a puzzle id; the router code already orders that way (post search, get random, get by_id) — insert it between `/random` and `/{puzzle_id}`.

- [ ] **Step 5: Run the tests and verify they pass**

```
pytest tests/test_puzzles_router.py -v
```
Expected: all green, including the three new tests.

- [ ] **Step 6: Commit**

```bash
git add app/models.py app/routers/puzzles.py tests/test_puzzles_router.py
git commit -m "$(cat <<'EOF'
feat(api): GET /api/puzzles/batch returns N random matching puzzles

Default limit 500, capped at 2000 server-side. Called once at session
start to warm the client-side pool; not per-puzzle.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Backend — `/play/{session_id}` HTML route

Serves the immersive session page. The session id stays in the URL for deep-linking and refresh-survival.

**Files:**
- Modify: `app/main.py`
- Create: `static/play.html` (placeholder this task — real layout in Task 7)
- Modify: `tests/test_main.py`

- [ ] **Step 1: Write the placeholder static file**

Create `static/play.html` with a minimal valid HTML body — the full layout is built in Task 7 but the file must exist for the route test to read it.

```html
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8"/>
<title>lichess-puzzles — sessão</title>
</head>
<body>
<main>
  <p>Sessão (Fase 2 — em construção).</p>
</main>
</body>
</html>
```

- [ ] **Step 2: Write the failing route test**

Append to `tests/test_main.py`:

```python
def test_play_route_serves_html(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/play/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "<!doctype html>" in r.text.lower()


def test_play_route_returns_maintenance_when_no_db(app_without_db) -> None:
    c = TestClient(app_without_db)
    r = c.get("/play/anything")
    assert r.status_code == 200
    assert "Banco ainda" in r.text
```

- [ ] **Step 3: Run the test and verify it fails**

```
pytest tests/test_main.py::test_play_route_serves_html -v
```
Expected: FAIL with 404.

- [ ] **Step 4: Add the route in `app/main.py`**

Insert below the `/explore` route:

```python
@app.get("/play/{session_id}", response_class=HTMLResponse)
def play(session_id: str) -> HTMLResponse:
    if not _db_exists():
        return HTMLResponse(MAINTENANCE_HTML)
    return HTMLResponse((STATIC_DIR / "play.html").read_text(encoding="utf-8"))
```

The `session_id` is accepted but not validated server-side: the client navigates here only after `POST /api/sessions` succeeds, and the page itself fetches `/api/sessions/{id}` to verify before starting. Server-side validation here would only force a duplicate round-trip.

- [ ] **Step 5: Run the tests and verify they pass**

```
pytest tests/test_main.py -v
```
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add app/main.py static/play.html tests/test_main.py
git commit -m "$(cat <<'EOF'
feat(routing): /play/{session_id} serves immersive session page

Placeholder HTML for now; the full board+clock layout lands in Task 7.
Route mirrors the maintenance fallback used by / and /explore.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Frontend — config screen layout (HTML + CSS)

Replace the Phase 1 stub with the real two-column config screen described in spec section 8.1: left column reuses the `/explore` filter widgets, right column has session knobs.

**Files:**
- Modify: `static/index.html`
- Modify: `static/css/config.css`

- [ ] **Step 1: Replace `static/index.html`**

Overwrite the file with:

```html
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>lichess-puzzles — configurar sessão</title>
<link rel="stylesheet" href="/static/css/styles.css"/>
<link rel="stylesheet" href="/static/css/config.css"/>
</head>
<body>
<header>
  <h1>lichess-puzzles</h1>
  <nav><a href="/explore">/explore ↗</a></nav>
</header>

<main class="config-main">
  <section class="panel filters-panel" id="filters">
    <h2>Filtros</h2>
    <div class="preset-row" id="presets"></div>

    <details open><summary>Básico</summary>
      <div class="row"><label>Rating</label>
        <input id="rating_min" type="number" placeholder="min">
        <input id="rating_max" type="number" placeholder="max"></div>
      <div class="row"><label>Nº peças</label>
        <input id="piece_count_min" type="number" placeholder="min">
        <input id="piece_count_max" type="number" placeholder="max"></div>
      <div class="row"><label>Nº do lance</label>
        <input id="move_number_min" type="number" placeholder="min">
        <input id="move_number_max" type="number" placeholder="max"></div>
      <div class="row"><label>Popularity ≥</label>
        <input id="popularity_min" type="number"></div>
      <div class="row"><label>NbPlays ≥</label>
        <input id="nb_plays_min" type="number"></div>
    </details>

    <details><summary>Derivados</summary>
      <div class="row"><label>Lado a mover</label>
        <select id="side_to_move"><option value="">—</option>
          <option value="w">Brancas</option><option value="b">Pretas</option></select></div>
      <div class="row"><label>Fase</label>
        <select id="phase"><option value="">—</option>
          <option value="opening">Abertura</option>
          <option value="middlegame">Meio-jogo</option>
          <option value="endgame">Final</option></select></div>
      <div class="row"><label>Material (B−P)</label>
        <input id="material_balance_min" type="number" placeholder="min">
        <input id="material_balance_max" type="number" placeholder="max"></div>
      <div class="row"><label>Promoção</label>
        <select id="has_promoted"><option value="">—</option>
          <option value="true">sim</option><option value="false">não</option></select></div>
      <div class="row"><label>En passant</label>
        <select id="has_en_passant"><option value="">—</option>
          <option value="true">sim</option><option value="false">não</option></select></div>
      <div class="row"><label>Roque disponível</label>
        <select id="has_castling"><option value="">—</option>
          <option value="true">sim</option><option value="false">não</option></select></div>
    </details>

    <details><summary>Themes (qualquer um)</summary>
      <div id="themes_any" class="checkbox-list"></div>
    </details>
    <details><summary>Themes (todos)</summary>
      <div id="themes_all" class="checkbox-list"></div>
    </details>
    <details><summary>Aberturas</summary>
      <div id="opening_tags_any" class="checkbox-list"></div>
    </details>

    <div class="filters-counter">
      Encontrados: <span id="counter">—</span>
    </div>
  </section>

  <section class="panel session-panel">
    <h2>Sessão</h2>

    <fieldset class="mode">
      <legend>Modo</legend>
      <label><input type="radio" name="mode" value="time" checked> Por tempo</label>
      <div class="mode-options" id="opts-time">
        <label><input type="radio" name="time-target" value="3"> 3 min</label>
        <label><input type="radio" name="time-target" value="5" checked> 5 min</label>
        <label><input type="radio" name="time-target" value="10"> 10 min</label>
        <label><input type="radio" name="time-target" value="custom"> outro
          <input type="number" id="time-custom" min="1" max="120" placeholder="min"></label>
      </div>
      <label><input type="radio" name="mode" value="count"> Por quantidade</label>
      <div class="mode-options" id="opts-count">
        <label><input type="radio" name="count-target" value="50"> 50</label>
        <label><input type="radio" name="count-target" value="100" checked> 100</label>
        <label><input type="radio" name="count-target" value="200"> 200</label>
        <label><input type="radio" name="count-target" value="500"> 500</label>
        <label><input type="radio" name="count-target" value="custom"> outro
          <input type="number" id="count-custom" min="1" max="9999" placeholder="puzzles"></label>
      </div>
      <label><input type="radio" name="mode" value="free" disabled> Modo livre <em>(Fase 4)</em></label>
    </fieldset>

    <fieldset class="extras">
      <label><input type="checkbox" id="dedupe_solved" checked> Não repetir resolvidos nesta sessão</label>
      <label><input type="checkbox" id="error_sound"> Som no erro <em>(Fase 5)</em></label>
      <label>Rótulo (opcional)
        <input type="text" id="label" maxlength="80" placeholder="ex.: Mate em 2"></label>
    </fieldset>

    <div class="pool-status">
      <button class="secondary" id="btn-pool">Buscar pool</button>
      <span id="pool-info">—</span>
    </div>

    <button class="primary" id="btn-start" disabled>Iniciar sessão</button>
    <div id="start-error" class="status-err" hidden></div>
  </section>

  <section class="panel sessions-panel">
    <h2>Sessões anteriores</h2>
    <ul id="sessions-list"><li class="empty">Carregando…</li></ul>
  </section>
</main>

<script type="importmap">
{
  "imports": {
    "chessground": "https://esm.sh/chessground@9.1.1",
    "chess.js":    "https://esm.sh/chess.js@1.0.0"
  }
}
</script>
<script type="module" src="/static/js/config.js"></script>
</body>
</html>
```

The chessground import map is unused on `/`, but it stays in the `<head>` section so future tooling (e.g., a tiny preview in Phase 5) can pick it up without HTML changes.

- [ ] **Step 2: Replace `static/css/config.css`**

Overwrite with:

```css
.config-main {
  display: grid;
  grid-template-columns: minmax(280px, 1fr) minmax(280px, 1fr);
  grid-template-rows: auto auto;
  gap: 1rem;
  max-width: 1100px;
  margin: 1rem auto;
  padding: 0 1rem;
}

.filters-panel  { grid-column: 1; grid-row: 1 / span 2; }
.session-panel  { grid-column: 2; grid-row: 1; }
.sessions-panel { grid-column: 2; grid-row: 2; }

@media (max-width: 720px) {
  .config-main { grid-template-columns: 1fr; }
  .filters-panel, .session-panel, .sessions-panel {
    grid-column: 1; grid-row: auto;
  }
}

.filters-panel h2,
.session-panel h2,
.sessions-panel h2 {
  margin: 0 0 .5rem 0;
  font-size: 1rem;
  color: #aaa;
  text-transform: uppercase;
  letter-spacing: .05em;
}

.filters-panel .preset-row {
  display: flex; flex-wrap: wrap; gap: .25rem;
  margin-bottom: .5rem;
}
.filters-panel .preset-row button {
  font-size: .85rem; padding: .15rem .5rem;
}

.filters-panel details { margin: .25rem 0; }
.filters-panel summary {
  cursor: pointer; padding: .25rem 0;
  font-size: .9rem; color: #ccc;
}
.filters-panel .row {
  display: flex; align-items: center; gap: .5rem;
  margin: .25rem 0;
}
.filters-panel .row label { flex: 0 0 8.5rem; font-size: .85rem; }
.filters-panel input[type=number],
.filters-panel select {
  width: 6rem; padding: .15rem .35rem;
}
.filters-panel .checkbox-list {
  max-height: 12rem; overflow-y: auto;
  display: grid; grid-template-columns: 1fr 1fr; gap: 0 .5rem;
  font-size: .85rem;
}
.filters-counter {
  margin-top: .5rem; font-size: .9rem; color: #aaa;
}

.session-panel fieldset {
  border: 1px solid #333; border-radius: .25rem;
  padding: .5rem .75rem; margin: 0 0 .75rem 0;
}
.session-panel fieldset legend {
  padding: 0 .35rem; color: #ccc; font-size: .85rem;
}
.session-panel fieldset label {
  display: block; padding: .15rem 0; font-size: .9rem;
}
.session-panel .mode-options {
  margin-left: 1.25rem; display: flex; flex-wrap: wrap; gap: .5rem;
}
.session-panel .mode-options label { display: inline-flex; align-items: center; gap: .25rem; }
.session-panel .mode-options input[type=number] {
  width: 5rem; padding: .1rem .25rem;
}
.session-panel .extras input[type=text] {
  width: 100%; padding: .25rem .5rem; margin-top: .15rem;
}
.session-panel .pool-status {
  display: flex; align-items: center; gap: .5rem; margin: .5rem 0;
}
.session-panel #pool-info { font-size: .9rem; color: #aaa; }
.session-panel #btn-start {
  width: 100%; padding: .5rem; font-size: 1rem;
}
.session-panel #btn-start:disabled { opacity: .5; cursor: not-allowed; }
.session-panel .status-err { color: #e66; font-size: .9rem; margin-top: .5rem; }

.sessions-panel ul { list-style: none; padding: 0; margin: 0; max-height: 18rem; overflow-y: auto; }
.sessions-panel li {
  display: grid;
  grid-template-columns: minmax(7rem, auto) minmax(5rem, auto) 1fr auto auto;
  gap: .5rem; padding: .25rem 0;
  border-bottom: 1px solid #222;
  font-size: .85rem;
}
.sessions-panel li.empty {
  grid-template-columns: 1fr; color: #666; font-style: italic;
}
.sessions-panel .when   { color: #aaa; }
.sessions-panel .target { color: #aaa; }
.sessions-panel .label  { color: #ccc; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sessions-panel .score  { color: #ccc; font-variant-numeric: tabular-nums; }
.sessions-panel .actions a {
  color: #6af; text-decoration: none; font-size: .9rem;
  padding: 0 .35rem;
}
.sessions-panel .actions a:hover { text-decoration: underline; }
```

This replaces the Phase 1 placeholder styles entirely; nothing in `/explore` reads `config.css`, so no migration needed.

- [ ] **Step 3: Smoke check (no automated test for static HTML)**

Run:
```
python -c "
from pathlib import Path
html = Path('static/index.html').read_text()
for needed in ['btn-pool', 'btn-start', 'mode', 'time-target', 'count-target',
               'dedupe_solved', 'sessions-list', 'rating_min', 'themes_any',
               'opening_tags_any', 'pool-info', 'label']:
    assert needed in html, f'missing id/name {needed}'
print('config screen markup ok')
"
```
Expected: `config screen markup ok`.

- [ ] **Step 4: Commit**

```bash
git add static/index.html static/css/config.css
git commit -m "$(cat <<'EOF'
feat(frontend): real config screen at / with filters + session knobs

Two-column layout: left reuses /explore's filter widgets, right has
mode (time/count, free disabled until Phase 4), target presets, dedupe
toggle, label, and pool warming controls. Sessões anteriores moves
under the session knobs.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Frontend — config.js wiring (filters + knobs + pool + start)

The behaviour: load themes/openings, render presets, debounce-update the counter, fetch the pool on demand, validate knobs, create the session and navigate. The previous-sessions list grows actionable links.

**Files:**
- Modify: `static/js/config.js` (rewrite)
- Modify: `static/js/api.js` (add three helpers)

- [ ] **Step 1: Add the API helpers**

Append to `static/js/api.js`:

```js
function filtersToQueryString(filtersForBatch) {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filtersForBatch)) {
    if (v === null || v === undefined || v === '') continue;
    if (Array.isArray(v)) v.forEach(val => params.append(k, val));
    else params.append(k, String(v));
  }
  return params.toString();
}

export async function fetchBatch(filters, limit = 500) {
  const qs = filtersToQueryString({ ...filters, limit });
  const r = await fetch(`/api/puzzles/batch${qs ? '?' + qs : ''}`);
  if (!r.ok) throw new Error('batch ' + r.status);
  return r.json();
}

export async function createSession(payload) {
  const r = await fetch('/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error('createSession ' + r.status);
  return r.json();
}

export async function listSessions(limit = 20) {
  const r = await fetch(`/api/sessions?limit=${limit}`);
  if (!r.ok) throw new Error('listSessions ' + r.status);
  return r.json();
}
```

The first `filtersToQueryString` already exists at the bottom of the file — leave it, the new copy is in module scope and is shadowed by the new exports above. (Since `api.js` is a module, the second `function` declaration with the same name is a `SyntaxError`. **Replace** the existing private `filtersToQueryString` rather than duplicating it: delete the old one at the bottom of the file. End state of `api.js` should have exactly one `filtersToQueryString` definition.)

- [ ] **Step 2: Rewrite `static/js/config.js`**

Overwrite the file with:

```js
import { initFilterUI, readFilters, updateCounter, applyPreset } from './filters.js';
import { fetchBatch, createSession, listSessions } from './api.js';

const POOL_LIMIT = 500;
const STORAGE_KEY = (sessionId) => `pool:${sessionId}`;

const state = {
  pool: null,            // { puzzles: [{puzzle_id, ...}], filtersSig: '...' }
  poolFiltersSig: null,
};

async function boot() {
  await initFilterUI(onFiltersChanged);

  const presets = await fetch('/static/presets.json').then(r => r.json());
  const row = document.getElementById('presets');
  presets.forEach(p => {
    const b = document.createElement('button');
    b.textContent = p.name;
    b.addEventListener('click', async () => {
      applyPreset(p.filters);
      await onFiltersChanged(readFilters());
    });
    row.append(b);
  });

  document.getElementById('btn-pool').addEventListener('click', onFetchPool);
  document.getElementById('btn-start').addEventListener('click', onStart);
  document.querySelectorAll('input[name=mode]').forEach(r =>
    r.addEventListener('change', refreshStartEnabled));
  document.querySelectorAll('.mode-options input').forEach(el =>
    el.addEventListener('input', refreshStartEnabled));

  await loadSessions();
  refreshStartEnabled();
}

function onFiltersChanged(filters) {
  state.pool = null;
  state.poolFiltersSig = null;
  setPoolInfo('—');
  updateCounter(filters);
  refreshStartEnabled();
}

function filtersSig(filters) {
  return JSON.stringify(filters, Object.keys(filters).sort());
}

async function onFetchPool() {
  const filters = readFilters();
  setPoolInfo('Buscando…');
  try {
    const data = await fetchBatch(filters, POOL_LIMIT);
    state.pool = data;
    state.poolFiltersSig = filtersSig(filters);
    if (data.count === 0) {
      setPoolInfo('Nenhum puzzle com esses filtros — afrouxe algum critério.');
    } else {
      setPoolInfo(`Pool pronta: ${data.count} puzzle${data.count === 1 ? '' : 's'}.`);
    }
  } catch (e) {
    setPoolInfo('Erro ao buscar: ' + e.message);
  }
  refreshStartEnabled();
}

function setPoolInfo(text) {
  document.getElementById('pool-info').textContent = text;
}

function readMode() {
  return document.querySelector('input[name=mode]:checked')?.value || 'time';
}

function readTarget(mode) {
  if (mode === 'free') return null;
  const groupName = mode === 'time' ? 'time-target' : 'count-target';
  const customId  = mode === 'time' ? 'time-custom' : 'count-custom';
  const sel = document.querySelector(`input[name=${groupName}]:checked`)?.value;
  if (sel === 'custom') {
    const v = Number(document.getElementById(customId).value);
    return Number.isFinite(v) && v > 0 ? v : null;
  }
  return sel ? Number(sel) : null;
}

function refreshStartEnabled() {
  const filters = readFilters();
  const mode = readMode();
  const target = readTarget(mode);
  const sigOk = state.poolFiltersSig === filtersSig(filters);
  const poolOk = sigOk && state.pool && state.pool.count > 0;
  const targetOk = mode === 'free' || (target !== null && target > 0);
  const ok = !!(poolOk && targetOk);
  const btn = document.getElementById('btn-start');
  btn.disabled = !ok;
  // Surface why the button is disabled, so the user does not have to guess.
  if (ok) {
    btn.title = '';
  } else if (!sigOk || !state.pool) {
    btn.title = 'Clique em "Buscar pool" para preparar o conjunto de puzzles.';
  } else if (!poolOk) {
    btn.title = 'Pool vazia — afrouxe os filtros.';
  } else if (!targetOk) {
    btn.title = 'Defina um alvo (preset ou outro com valor > 0).';
  }
}

async function onStart() {
  hideStartError();
  const filters = readFilters();
  const mode = readMode();
  const target = readTarget(mode);
  const dedupe = document.getElementById('dedupe_solved').checked;
  const labelEl = document.getElementById('label');
  const label = labelEl.value.trim() || null;

  if (state.poolFiltersSig !== filtersSig(filters)) {
    showStartError('Os filtros mudaram após o "Buscar pool". Clique de novo.');
    return;
  }
  if (!state.pool || state.pool.count === 0) {
    showStartError('Pool vazia.');
    return;
  }

  // Clamp the target to the pool size when the user asked for more puzzles than
  // we have. Spec section 8.1: "se pool < target, ajustar para N".
  let effectiveTarget = target;
  if (mode === 'count' && target !== null && target > state.pool.count) {
    effectiveTarget = state.pool.count;
  }

  document.getElementById('btn-start').disabled = true;
  try {
    const created = await createSession({
      mode,
      target: effectiveTarget,
      auto_advance: true,
      dedupe_solved: dedupe,
      filters,
      parent_session: null,
      label,
    });
    sessionStorage.setItem(STORAGE_KEY(created.session_id), JSON.stringify({
      puzzle_ids: state.pool.puzzles.map(p => p.puzzle_id),
    }));
    location.href = `/play/${created.session_id}`;
  } catch (e) {
    showStartError('Falha ao criar sessão: ' + e.message);
    document.getElementById('btn-start').disabled = false;
  }
}

function showStartError(msg) {
  const el = document.getElementById('start-error');
  el.textContent = msg; el.hidden = false;
}
function hideStartError() { document.getElementById('start-error').hidden = true; }

async function loadSessions() {
  const ul = document.getElementById('sessions-list');
  try {
    const list = await listSessions(20);
    if (list.length === 0) {
      ul.innerHTML = '<li class="empty">Nenhuma sessão ainda.</li>';
      return;
    }
    ul.innerHTML = '';
    for (const s of list) {
      const li = document.createElement('li');
      li.innerHTML = `
        <span class="when">${formatStarted(s.started_at)}</span>
        <span class="target">${formatTarget(s.mode, s.target)}</span>
        <span class="label">${escapeHtml(s.label || '')}</span>
        <span class="score">${s.correct}/${s.total}</span>
        <span class="actions">
          <a href="/play/${s.session_id}" title="Reabrir">→</a>
        </span>
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
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
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

boot().catch(e => {
  document.getElementById('pool-info').textContent = 'Erro ao iniciar: ' + e.message;
});
```

The previous-session row links via `[→]` (single anchor) only; the redo (`[↻]`) action that the spec mentions belongs to the stats screen and lands in Phase 3.

- [ ] **Step 3: Manual smoke**

Start the server (`make serve` or `uvicorn app.main:app`) and visit `http://localhost:8000/`.

Verify:
- Filters load (themes and openings populate).
- Counter updates with debounce.
- Clicking a preset applies the filters; counter changes; *Iniciar* stays disabled until pool is fetched.
- *Buscar pool* shows "Pool pronta: N puzzles".
- Picking *count* + 50 (or 100) and clicking *Iniciar* navigates to `/play/<uuid>` (placeholder page from Task 3 for now).
- Refreshing `/` shows the new session in *Sessões anteriores*.

(No automated frontend tests — continues current policy.)

- [ ] **Step 4: Commit**

```bash
git add static/js/config.js static/js/api.js
git commit -m "$(cat <<'EOF'
feat(frontend): config-screen wiring (pool warm + create session)

Filter changes invalidate the pool. Buscar pool fetches up to 500
puzzles. Iniciar validates target/pool, creates the session, transfers
the puzzle id list via sessionStorage, and navigates to /play/:id.
Sessões anteriores grows a [→] link per row.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Frontend — `/explore` "session ended" banner

When the trainer ends a session it sends the user to `/explore?ended=:id`. A small banner acknowledges this so the user does not feel tossed. Phase 3 will replace this redirect with the real stats screen.

**Files:**
- Modify: `static/explore.html`
- Modify: `static/js/explore.js`

- [ ] **Step 1: Add the banner element**

In `static/explore.html`, insert directly after `<header>...</header>`:

```html
<div id="ended-banner" class="ended-banner" hidden></div>
```

- [ ] **Step 2: Add minimal CSS**

Append to `static/css/styles.css`:

```css
.ended-banner {
  background: #2a3b2a; color: #cfe; border: 1px solid #3a5;
  padding: .5rem 1rem; margin: .5rem 1rem; border-radius: .25rem;
  font-size: .9rem;
}
.ended-banner a { color: #9fb; }
```

- [ ] **Step 3: Read the query param and render the banner**

Insert at the top of the `boot` function in `static/js/explore.js`, before `const trainer = createTrainer();`:

```js
  const params = new URLSearchParams(location.search);
  const endedId = params.get('ended');
  if (endedId) {
    const banner = document.getElementById('ended-banner');
    banner.innerHTML = `Sessão <code>${endedId.slice(0, 8)}</code> encerrada.
      Estatísticas detalhadas chegam na Fase 3 — voltar à
      <a href="/">configuração</a>.`;
    banner.hidden = false;
  }
```

- [ ] **Step 4: Manual smoke**

Open `http://localhost:8000/explore?ended=demo-id-123` and confirm the green banner shows the truncated id and the home link. Closing the tab clears it (no persistent state).

- [ ] **Step 5: Commit**

```bash
git add static/explore.html static/js/explore.js static/css/styles.css
git commit -m "$(cat <<'EOF'
feat(frontend): /explore acknowledges ?ended=:id with a banner

Phase 3 replaces this with the real stats screen; for Phase 2 the
trainer just returns the user here with a truncated session id.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Frontend — `play.html` immersive layout + CSS

Replace the placeholder from Task 3 with the real layout: top bar (clock + counter + encerrar), centered board, dark neutral background.

**Files:**
- Modify: `static/play.html`
- Create: `static/css/play.css`

- [ ] **Step 1: Overwrite `static/play.html`**

```html
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>lichess-puzzles — sessão</title>
<link rel="stylesheet" href="/static/vendor/chessground.base.css"/>
<link rel="stylesheet" href="/static/vendor/chessground.brown.css"/>
<link rel="stylesheet" href="/static/vendor/chessground.cburnett.css"/>
<link rel="stylesheet" href="/static/css/styles.css"/>
<link rel="stylesheet" href="/static/css/play.css"/>
<script type="importmap">
{
  "imports": {
    "chessground": "https://esm.sh/chessground@9.1.1",
    "chess.js":    "https://esm.sh/chess.js@1.0.0"
  }
}
</script>
</head>
<body class="play-body">
<div class="play-shell">
  <header class="play-bar">
    <div class="play-clock" id="clock">00:00</div>
    <div class="play-counter" id="counter">0 / 0</div>
    <button class="play-quit" id="btn-quit" title="Encerrar sessão">⏹ encerrar</button>
  </header>

  <main class="play-board-wrap">
    <div id="board" class="play-board"></div>
    <div id="flash" class="play-flash" aria-live="polite"></div>
  </main>

  <div class="play-overlay" id="overlay" hidden>
    <div class="play-overlay-card">
      <p id="overlay-msg"></p>
      <button class="primary" id="overlay-action">OK</button>
    </div>
  </div>
</div>

<script type="module" src="/static/js/play.js"></script>
</body>
</html>
```

- [ ] **Step 2: Create `static/css/play.css`**

```css
.play-body { background: #1a1a1a; margin: 0; }
.play-shell {
  min-height: 100vh; display: flex; flex-direction: column;
  align-items: center;
}

.play-bar {
  width: 100%; max-width: 90vmin;
  display: grid; grid-template-columns: 1fr 1fr 1fr;
  align-items: center;
  padding: .75rem 1rem; box-sizing: border-box;
}
.play-clock {
  font-size: 2.5rem; font-variant-numeric: tabular-nums;
  text-align: left; color: #ddd;
}
.play-clock.warning { color: #fa6; }
.play-clock.urgent  { color: #f55; }
.play-counter {
  font-size: 1.25rem; text-align: center; color: #ccc;
  font-variant-numeric: tabular-nums;
}
.play-quit {
  justify-self: end; opacity: .4; transition: opacity .15s;
  background: none; border: 1px solid #444; color: #ccc;
  padding: .35rem .75rem; border-radius: .25rem;
  font-size: .9rem; cursor: pointer;
}
.play-quit:hover { opacity: 1; border-color: #888; }

.play-board-wrap {
  position: relative;
  width: min(70vh, 90vw); aspect-ratio: 1 / 1;
  margin: 1rem 0;
}
.play-board { position: absolute; inset: 0; }

.play-flash {
  position: absolute; left: 0; right: 0; bottom: -1.75rem;
  text-align: center; font-size: 1rem;
  pointer-events: none;
}
.play-flash.ok  { color: #6f9; }
.play-flash.err { color: #f66; }

.play-board-wrap.shake { animation: shake .2s; }
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  25%      { transform: translateX(-6px); }
  75%      { transform: translateX( 6px); }
}

.play-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.7);
  display: flex; align-items: center; justify-content: center;
  z-index: 10;
}
.play-overlay-card {
  background: #222; border: 1px solid #444; border-radius: .5rem;
  padding: 1.5rem; max-width: 28rem; text-align: center;
}
.play-overlay-card p { margin: 0 0 1rem 0; color: #ddd; }
```

- [ ] **Step 3: Manual smoke**

Visit `/play/anything-uuid`. Expected:
- dark background
- top bar with `00:00` clock, `0 / 0` counter, and a faint *encerrar* button
- empty centered board placeholder (chessground not yet wired)
- no JS errors in console (404 on `/static/js/play.js` is acceptable here — the file is created in Task 8)

- [ ] **Step 4: Commit**

```bash
git add static/play.html static/css/play.css
git commit -m "$(cat <<'EOF'
feat(frontend): immersive /play layout (board + clock + counter)

No platform header, dark background, board centered to 70vh, discreet
encerrar button (opacity .4 → 1 on hover), and a hidden overlay used
for end-of-session messaging.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Frontend — `play.js` skeleton: pool load, session resolve, board mount

Sets up the page: read session id from URL, resolve session metadata (target/mode), pop the pool from sessionStorage, mount chessground. No state machine yet — that lands in Task 9.

**Files:**
- Create: `static/js/play.js`

- [ ] **Step 1: Create the file**

```js
import { Chessground } from 'chessground';
import { Chess } from 'chess.js';

const STORAGE_KEY = (sessionId) => `pool:${sessionId}`;

const session = {
  id: null,
  meta: null,         // { mode, target, auto_advance, ... }
  pool: [],           // [puzzle_id]
  poolIdx: 0,
  attempts: [],       // [{ order_idx, puzzle_id, correct, time_ms }]
  ended: false,
};

const ui = {
  board: null,
  chess: null,
  puzzle: null,
  moveIndex: 0,
  exerciseStartedAt: 0,
  state: 'IDLE',      // 'PREVIEW' | 'OPPONENT_MOVE' | 'USER_TURN' | 'OUTCOME' | 'IDLE'
};

async function boot() {
  session.id = location.pathname.split('/').pop();

  const [meta, stored] = [
    await fetchSession(session.id),
    JSON.parse(sessionStorage.getItem(STORAGE_KEY(session.id)) || 'null'),
  ];
  session.meta = meta.session;
  if (session.meta.ended_at) {
    return showOverlay('Esta sessão já está encerrada.', 'Voltar', goExplore);
  }
  if (!stored || !Array.isArray(stored.puzzle_ids) || stored.puzzle_ids.length === 0) {
    return showOverlay(
      'Pool não encontrada para esta sessão. Volte e clique em "Buscar pool" novamente.',
      'Voltar', () => location.href = '/'
    );
  }
  session.pool = stored.puzzle_ids;

  ui.board = Chessground(document.getElementById('board'), {
    movable: { free: false, color: null, events: { after: onUserMove } },
    draggable: { showGhost: true },
  });

  document.getElementById('btn-quit').addEventListener('click', onQuit);
  renderCounter();
  renderClock(0);
  await loadNextPuzzle();
}

async function fetchSession(id) {
  const r = await fetch(`/api/sessions/${id}`);
  if (!r.ok) throw new Error('session ' + r.status);
  return r.json();
}

async function loadPuzzleById(id) {
  const r = await fetch(`/api/puzzles/${id}`);
  if (!r.ok) throw new Error('puzzle ' + r.status);
  return r.json();
}

async function loadNextPuzzle() {
  if (session.poolIdx >= session.pool.length) {
    return endSession('count');  // pool exhausted is treated as "count" for now
  }
  const id = session.pool[session.poolIdx++];
  ui.puzzle = await loadPuzzleById(id);
  ui.chess = new Chess(ui.puzzle.fen);
  ui.moveIndex = 0;
  startPreview();
}

function startPreview() {
  // PREVIEW: show FEN, board inert, opponent to move.
  // The user sits behind the side OPPOSITE to fen.side_to_move.
  const oppColor = ui.puzzle.side_to_move === 'w' ? 'white' : 'black';
  const userColor = oppColor === 'white' ? 'black' : 'white';
  ui.board.set({
    fen: ui.chess.fen(),
    turnColor: oppColor,
    orientation: userColor,
    movable: { color: null, dests: new Map() },
    lastMove: undefined,
    drawable: { autoShapes: [] },
  });
  ui.state = 'PREVIEW';
  setFlash('');
  setTimeout(startOpponentMove, 400);
}

function startOpponentMove() {
  const moves = ui.puzzle.moves.split(' ');
  const uci = moves[0];
  ui.chess.move({ from: uci.slice(0,2), to: uci.slice(2,4), promotion: uci[4] });
  ui.moveIndex = 1;
  ui.board.set({
    fen: ui.chess.fen(),
    lastMove: [uci.slice(0,2), uci.slice(2,4)],
    movable: { color: null, dests: new Map() },
  });
  ui.state = 'OPPONENT_MOVE';
  // Allow chessground to animate before unlocking the user.
  setTimeout(armUserTurn, 250);
}

function armUserTurn() {
  const userColor = ui.puzzle.side_to_move === 'w' ? 'black' : 'white';
  ui.board.set({
    turnColor: userColor,
    movable: {
      color: userColor,
      free: false,
      dests: legalDests(ui.chess),
      events: { after: onUserMove },
    },
  });
  ui.state = 'USER_TURN';
  ui.exerciseStartedAt = performance.now();
}

function onUserMove(orig, dest) {
  // Stub for now — full implementation in Task 9.
  ui.chess.undo();
  ui.board.set({ fen: ui.chess.fen() });
}

function legalDests(chess) {
  const dests = new Map();
  for (const f of 'abcdefgh') for (const r of '12345678') {
    const sq = f + r;
    const moves = chess.moves({ square: sq, verbose: true });
    if (moves.length) dests.set(sq, moves.map(m => m.to));
  }
  return dests;
}

function setFlash(msg, kind) {
  const el = document.getElementById('flash');
  el.textContent = msg;
  el.className = 'play-flash ' + (kind || '');
}

function renderCounter() {
  const total = session.attempts.length;
  const correct = session.attempts.filter(a => a.correct).length;
  let text;
  if (session.meta.mode === 'count') {
    text = `${correct} / ${session.meta.target ?? '?'}`;
  } else {
    const wrong = total - correct;
    text = `✓ ${correct}  ✗ ${wrong}`;
  }
  document.getElementById('counter').textContent = text;
}

function renderClock(elapsedMs) {
  const el = document.getElementById('clock');
  let secs;
  if (session.meta.mode === 'time') {
    const remaining = Math.max(0, (session.meta.target * 60_000) - elapsedMs);
    secs = Math.ceil(remaining / 1000);
    el.classList.toggle('warning', secs <= 30 && secs > 10);
    el.classList.toggle('urgent', secs <= 10);
  } else {
    secs = Math.floor(elapsedMs / 1000);
  }
  const m = Math.floor(secs / 60).toString().padStart(2, '0');
  const s = (secs % 60).toString().padStart(2, '0');
  el.textContent = `${m}:${s}`;
}

function showOverlay(msg, actionLabel, onAction) {
  document.getElementById('overlay-msg').textContent = msg;
  const btn = document.getElementById('overlay-action');
  btn.textContent = actionLabel;
  btn.onclick = onAction;
  document.getElementById('overlay').hidden = false;
}

function goExplore() {
  location.href = '/explore?ended=' + encodeURIComponent(session.id);
}

async function onQuit() {
  if (!confirm('Encerrar a sessão agora?')) return;
  await endSession('manual');
}

async function endSession(reason) {
  if (session.ended) return;
  session.ended = true;
  try {
    await fetch(`/api/sessions/${session.id}/end`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ end_reason: reason }),
    });
  } catch { /* server-side guarantee not critical for redirect */ }
  goExplore();
}

boot().catch(e => {
  showOverlay('Erro ao iniciar a sessão: ' + (e.message || e), 'Voltar', goExplore);
});
```

- [ ] **Step 2: Manual smoke**

Visit `/play/<uuid-from-a-real-session>` (open `/`, *Buscar pool*, *Iniciar*).

Expected behaviour:
- Board renders with the user's side at the bottom (orientation flipped relative to FEN.side_to_move).
- ~400 ms after load, the opponent's first move animates on the board.
- ~250 ms later, the board unlocks for the user (you can drag a piece — it bounces back because Task 9 hasn't shipped yet).
- Counter shows `0 / target` (count mode) or `✓ 0 ✗ 0` (time mode).
- Clock counts down (time) or up (count).
- Clicking *Encerrar* prompts and sends the user to `/explore?ended=<id>`.

- [ ] **Step 3: Commit**

```bash
git add static/js/play.js
git commit -m "$(cat <<'EOF'
feat(frontend): play.js skeleton with PREVIEW->OPPONENT_MOVE->USER_TURN

Reads session id from URL, fetches /api/sessions/{id} to resolve
mode/target, pulls puzzle id list from sessionStorage, mounts
chessground, plays the first opponent move automatically, and arms
the user's turn through chessground's `after` callback. Move
validation is stubbed; full validation lands next task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Frontend — `play.js` move validation (fail-fast + mate-in-N)

Implements `onUserMove` per spec section 6.2: legal-move check, expected-UCI match, mate-in-N alternative on the last move, register attempt and advance.

**Files:**
- Modify: `static/js/play.js`

- [ ] **Step 1: Replace `onUserMove`**

Find the stub `function onUserMove(...)` and replace it with:

```js
function onUserMove(orig, dest) {
  if (ui.state !== 'USER_TURN') return;

  const moves = ui.puzzle.moves.split(' ');
  const expectedUci = moves[ui.moveIndex];
  const isLastMove = ui.moveIndex === moves.length - 1;
  const isMatePuzzle = (ui.puzzle.themes || []).some(t => t.startsWith('mate'));
  const expectedPromo = expectedUci.length === 5 ? expectedUci[4] : undefined;

  // Try the move with the expected promotion if any. If chess.js refuses
  // (illegal, including wrong promotion), it's wrong.
  const played = ui.chess.move({ from: orig, to: dest, promotion: expectedPromo });
  if (!played) {
    return registerWrongAndAdvance();
  }
  const userUci = played.from + played.to + (played.promotion || '');

  if (userUci === expectedUci) {
    return continueAfterCorrect(moves);
  }
  if (isLastMove && isMatePuzzle && ui.chess.isCheckmate()) {
    return continueAfterCorrect(moves);
  }

  // Wrong but legal: undo so the position resets visually before the next puzzle.
  ui.chess.undo();
  registerWrongAndAdvance();
}

function continueAfterCorrect(moves) {
  ui.moveIndex += 1;
  // Refresh the board to reflect the user's move (chessground already animated it,
  // but we want to be sure FEN/lastMove/turnColor are consistent for the inert window).
  ui.board.set({
    fen: ui.chess.fen(),
    movable: { color: null, dests: new Map() },
    turnColor: ui.chess.turn() === 'w' ? 'white' : 'black',
  });
  ui.state = 'OPPONENT_REPLY';

  if (ui.moveIndex >= moves.length) {
    return registerCorrectAndAdvance();
  }

  // Apply the opponent's automatic reply after a short pause.
  setTimeout(() => {
    const reply = moves[ui.moveIndex];
    ui.chess.move({ from: reply.slice(0,2), to: reply.slice(2,4), promotion: reply[4] });
    ui.moveIndex += 1;
    ui.board.set({
      fen: ui.chess.fen(),
      lastMove: [reply.slice(0,2), reply.slice(2,4)],
    });
    if (ui.moveIndex >= moves.length) {
      registerCorrectAndAdvance();
    } else {
      // Hand the board back to the user.
      const userColor = ui.puzzle.side_to_move === 'w' ? 'black' : 'white';
      ui.board.set({
        turnColor: userColor,
        movable: {
          color: userColor, free: false,
          dests: legalDests(ui.chess), events: { after: onUserMove },
        },
      });
      ui.state = 'USER_TURN';
    }
  }, 250);
}

function registerCorrectAndAdvance() {
  recordAttempt(true);
  setFlash('✓', 'ok');
  ui.state = 'OUTCOME';
  setTimeout(loadNextPuzzle, 350);
}

function registerWrongAndAdvance() {
  recordAttempt(false);
  setFlash('✗', 'err');
  document.querySelector('.play-board-wrap').classList.add('shake');
  setTimeout(() =>
    document.querySelector('.play-board-wrap').classList.remove('shake'), 250);
  ui.state = 'OUTCOME';
  setTimeout(loadNextPuzzle, 600);
}

function recordAttempt(correct) {
  const attempt = {
    order_idx: session.attempts.length,
    puzzle_id: ui.puzzle.puzzle_id,
    correct,
    time_ms: Math.round(performance.now() - ui.exerciseStartedAt),
  };
  session.attempts.push(attempt);
  postAttempt(attempt);
  renderCounter();
}

function postAttempt(attempt, retriesLeft = 3) {
  fetch(`/api/sessions/${session.id}/attempts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(attempt),
  }).then(r => {
    if (!r.ok && r.status !== 409 && retriesLeft > 0) {
      setTimeout(() => postAttempt(attempt, retriesLeft - 1), 1500);
    }
  }).catch(() => {
    if (retriesLeft > 0) setTimeout(() => postAttempt(attempt, retriesLeft - 1), 1500);
  });
}
```

The `OPPONENT_REPLY` state is implicit — kept as a string label only for debugging (`ui.state` shows up in dev tools). It does not gate any logic; the stale-callback guard is `state !== 'USER_TURN'` at the top of `onUserMove`.

- [ ] **Step 2: Manual smoke (correct path)**

Run a session with a Mate-em-1 preset (5 puzzles is enough). For each puzzle:
- The opponent's move animates first.
- Playing the expected mate move should flash `✓` and load the next puzzle ~350 ms later.
- Counter increments to `1`, `2`, `3`, ... after each correct.

- [ ] **Step 3: Manual smoke (wrong path)**

For one puzzle, deliberately play a non-mate legal move. Expected:
- Board shakes, flash shows `✗`, position is restored.
- After ~600 ms, the next puzzle starts.
- Counter shows `✓ 1 ✗ 1` (in time mode) or no change (in count mode the wrong attempt does NOT increment the success counter).

- [ ] **Step 4: Manual smoke (mate-in-N alternative)**

Pick a Mate-em-2 puzzle. On the LAST user move, instead of the recorded UCI, play a different legal mate (if one exists; many mate-in-2 puzzles have only one mate, in which case skip this case). Expected: still counted as `✓`.

For an intermediate (non-last) move in a mate-in-2, playing a different move that happens to also be legal but is not the expected UCI should be counted as `✗` (not as an alternative mate, because `isLastMove` is false).

- [ ] **Step 5: Confirm `attempts` rows in DB**

After the session, run:
```
sqlite3 puzzles.sqlite "SELECT order_idx, puzzle_id, correct, time_ms FROM attempts WHERE session_id='<uuid>' ORDER BY order_idx;"
```
Expected: one row per puzzle attempted, with `time_ms` between ~200 and ~30000. Repeat with a session in time mode and verify there are no rows with `correct` other than 0/1.

- [ ] **Step 6: Commit**

```bash
git add static/js/play.js
git commit -m "$(cat <<'EOF'
feat(frontend): fail-fast move validation + mate-in-N alternative

Illegal or non-matching user moves register correct=0 and auto-advance
in ~600 ms (with red shake). Multi-move correct sequences animate the
opponent reply, then re-arm the user. Mate-in-N puzzles accept any
legal mate as the final move via chess.isCheckmate().

Attempts are POSTed fire-and-forget with up to 3 retries; the trainer
never blocks on telemetry.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Frontend — `play.js` clock + termination + dedupe

Drives the on-screen clock, ends the session at the right moment, and skips already-solved puzzles within the same session when `dedupe_solved` is on.

**Files:**
- Modify: `static/js/play.js`

- [ ] **Step 1: Drive the clock with a single rAF loop**

Add at the top of `play.js`, near the other state objects:

```js
const clock = { startedAt: 0, raf: 0 };
```

Add a `startClockLoop` function and a `tick` function:

```js
function startClockLoop() {
  clock.startedAt = performance.now();
  const tick = () => {
    if (session.ended) return;
    const elapsed = performance.now() - clock.startedAt;
    renderClock(elapsed);
    if (session.meta.mode === 'time' &&
        elapsed >= session.meta.target * 60_000) {
      endSession('time');
      return;
    }
    clock.raf = requestAnimationFrame(tick);
  };
  clock.raf = requestAnimationFrame(tick);
}
```

Call `startClockLoop()` at the end of the existing `boot()` function, immediately before `await loadNextPuzzle();`. Replace the existing line `renderClock(0);` with `startClockLoop();` (which also calls `renderClock` on first tick).

Final state of the relevant fragment in `boot`:
```js
  document.getElementById('btn-quit').addEventListener('click', onQuit);
  renderCounter();
  startClockLoop();
  await loadNextPuzzle();
```

- [ ] **Step 2: Honor `dedupe_solved`**

Add a small helper and use it inside `recordAttempt`:

```js
const solvedThisSession = new Set();
```
(declare near `session` and `ui`).

Inside `recordAttempt`, after `session.attempts.push(attempt)`, append:
```js
  if (correct) solvedThisSession.add(attempt.puzzle_id);
```

And modify `loadNextPuzzle` so it skips already-solved puzzles when the session has `dedupe_solved`:

```js
async function loadNextPuzzle() {
  while (session.poolIdx < session.pool.length) {
    const id = session.pool[session.poolIdx++];
    if (session.meta.dedupe_solved && solvedThisSession.has(id)) continue;
    ui.puzzle = await loadPuzzleById(id);
    ui.chess = new Chess(ui.puzzle.fen);
    ui.moveIndex = 0;
    startPreview();
    return;
  }
  endSession('count');
}
```

(`dedupe_solved` flag is already on the session metadata returned by `GET /api/sessions/{id}`.)

- [ ] **Step 3: End in count mode at target**

Inside `recordAttempt`, after `renderCounter()`, append:
```js
  if (session.meta.mode === 'count') {
    const correct = session.attempts.filter(a => a.correct).length;
    if (session.meta.target !== null && correct >= session.meta.target) {
      // Defer to give the success flash time to render.
      setTimeout(() => endSession('count'), 400);
    }
  }
```

This counts *correct* answers against the target — the spec section 8.1 counter is "✓ correct / target". A user playing 200 puzzles with 50% accuracy in `count: 100` mode keeps going until they reach 100 correct, which matches the Lumosity-style "target reached" feedback the user described in the brainstorm.

- [ ] **Step 4: Cancel the rAF on end**

Inside `endSession`, before the `try { ... }` block, insert:
```js
  if (clock.raf) cancelAnimationFrame(clock.raf);
```

- [ ] **Step 5: Manual smoke (time mode)**

Start a 1-minute time-mode session (via the *outro* custom input). Confirm:
- Clock counts down from `01:00`.
- At `:30` the clock turns orange.
- At `:10` it turns red.
- At `00:00` the page redirects to `/explore?ended=<id>` and the green banner shows.
- DB: `sqlite3 puzzles.sqlite "SELECT mode, target, end_reason FROM sessions WHERE session_id=...;"` returns `('time', 1, 'time')`.

- [ ] **Step 6: Manual smoke (count mode + dedupe)**

Start a count=5 session. Try to fail one puzzle, then solve five total. Confirm:
- Counter ends at `5 / 5`.
- Page redirects to `/explore?ended=<id>`.
- DB: `end_reason='count'` and `attempts` has at least 5 rows with `correct=1` plus any with `correct=0`.

If you replay the same puzzle id by manipulating the pool (or simply pass through the same id twice in a debug session), the second exposure should be skipped silently because `solvedThisSession` saw the first correct attempt.

- [ ] **Step 7: Commit**

```bash
git add static/js/play.js
git commit -m "$(cat <<'EOF'
feat(frontend): clock loop + count termination + within-session dedupe

Single rAF tick drives the clock; warning/urgent classes light up the
last 30s/10s in time mode. Count mode ends 400 ms after the target's
correct attempt. dedupe_solved skips repeats within the same session.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Backend — `attempts.completed_at` returned by `GET /api/sessions/{id}`

Spot check while wiring everything: the `completed_at` field on `AttemptDetail` is currently populated by `_now_iso()` server-side. Phase 3's stats screen will need it. Verify nothing regressed by reading back attempts via the API.

**Files:**
- Modify: `tests/test_sessions.py`

- [ ] **Step 1: Add a regression test**

Append to `tests/test_sessions.py`:

```python
def test_get_session_returns_attempt_completed_at(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.post("/api/sessions", json={
        "mode": "count", "target": 1,
        "auto_advance": True, "dedupe_solved": False,
        "filters": {}, "parent_session": None, "label": "regression",
    })
    sid = r.json()["session_id"]
    c.post(f"/api/sessions/{sid}/attempts", json={
        "order_idx": 0, "puzzle_id": "00008", "correct": True, "time_ms": 1234,
    })
    body = c.get(f"/api/sessions/{sid}").json()
    assert len(body["attempts"]) == 1
    a = body["attempts"][0]
    assert a["completed_at"] and "T" in a["completed_at"]
    assert a["time_ms"] == 1234
    assert a["rating"] >= 0   # joined from puzzles
```

- [ ] **Step 2: Run the suite**

```
pytest -q
```
Expected: all green, including the regression test.

- [ ] **Step 3: Commit**

```bash
git add tests/test_sessions.py
git commit -m "$(cat <<'EOF'
test(sessions): regression for completed_at + rating join on attempts

Phase 3 stats screen relies on these fields; lock them in now.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: End-to-end manual smoke + Phase-2 close-out

A guided walkthrough exercising every Phase-2 deliverable. No code changes here; this task is the explicit go/no-go.

**Files:** none

- [ ] **Step 1: Run the suite**

```
pytest -q
```
Expected: ~80+ tests pass, 0 failures.

- [ ] **Step 2: Run the server**

```
make serve
```
(or `uvicorn app.main:app --reload`)

- [ ] **Step 3: Walk through `/`**

- Page loads two columns + previous-sessions list.
- Apply preset *Mate em 1*. Counter shows a positive number.
- *Buscar pool* → "Pool pronta: N puzzles".
- Pick mode *Por quantidade* → 50.
- Type a label "smoke-phase2".
- Click *Iniciar*.

- [ ] **Step 4: Walk through `/play/:id`**

- Board orientation matches the user side.
- First puzzle: opponent move plays automatically; clock starts; counter `0 / 50`.
- Solve 3 puzzles; intentionally fail 1; confirm shake + flash + auto-advance.
- Counter shows `✓ 3 / 50` (or with `✗` in non-count modes).
- Click *Encerrar*; confirm; redirected to `/explore?ended=<id>` with banner.

- [ ] **Step 5: DB inspection**

```
sqlite3 puzzles.sqlite "
SELECT s.session_id, s.mode, s.target, s.label, s.end_reason,
       COUNT(a.order_idx) AS attempts,
       SUM(a.correct) AS correct
FROM sessions s LEFT JOIN attempts a USING (session_id)
WHERE s.label='smoke-phase2'
GROUP BY s.session_id;"
```
Expected: one row, mode `count`, target `50`, attempts ≥ 4, correct ≥ 3, end_reason `manual`.

- [ ] **Step 6: Repeat in time mode**

Start a 1-min time-mode session, label "smoke-phase2-time". Let the timer run out without playing. Confirm:
- Auto-redirect at `00:00`.
- DB row has `end_reason='time'` and `ended_at IS NOT NULL` and 0 attempts.

- [ ] **Step 7: Confirm `/explore` is unchanged**

Visit `/explore` directly (no `?ended` param). Verify the old single-page UI is exactly as before — no banner, no extra panels, search/random/reveal/reset buttons all work.

- [ ] **Step 8: Commit a Phase-2 marker**

```bash
git commit --allow-empty -m "$(cat <<'EOF'
chore: Phase 2 (correct trainer) end-to-end smoke passed

All success criteria from the Phase-2 plan validated against a
populated puzzles.sqlite.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Out of scope (deferred to later phases)

- Stats screen (`/play/:id/stats`) — Phase 3.
- *Refazer errados* link from previous sessions — needs the stats screen first.
- Free mode (`mode=free`, manual advance, variant nav, sandbox) — Phase 4.
- Confirm modal styling, error sound, A11y polish — Phase 5.
- Performance plan B for `ORDER BY RANDOM` if it turns out to be > 2 s on broad filters — measure first; ungate Phase 5.
