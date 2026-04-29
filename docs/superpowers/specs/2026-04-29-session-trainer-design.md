# Session Trainer — Design Spec

**Date:** 2026-04-29
**Author:** Gustavo von Atzingen
**Status:** Draft (awaiting user review)
**Supersedes:** parts of `2026-04-18-lichess-puzzles-design.md` (extends, does not replace)

## 1. Context and goal

The current platform (`/`) shows filters, board, and puzzle info on the same
single-page screen. It works as a curation/exploration tool but has flaws as a
training instrument: the FEN is loaded directly on the user's turn (skipping
the "before the opponent's mistake" preview), the puzzle auto-advances 1.5s
after solving (no explicit user action), there is no concept of a delimited
training session, and there are no statistics.

The goal of this spec is to design a **second mode of operation** — a
session-based, immersive trainer aimed at fast pattern recognition, modeled
after Puzzle Storm/Rush but restricted to puzzles the user can solve in 1-2
seconds (controlled via filters). The user explicitly described the analogy
with Lumosity's RainDrops and a CS round: a delimited block of intense focus
with feedback at the end.

The current single-page screen is preserved unchanged at `/explore` as a
curation tool. The new trainer becomes the front door at `/`.

## 2. Decisions taken during brainstorming

| # | Question | Decision |
|---|---|---|
| 1 | Coexistence vs replacement | Coexist: `/` = trainer, `/explore` = current page |
| 2 | Wrong-move handling | Fail-fast with internal marking; redo failed at end |
| 3 | Session termination mode | Time XOR count (3/5/10 min, 50/100/200/500 + free input) + secondary "free mode" + always-available "encerrar agora" |
| 4 | Per-puzzle transition | Default auto-advance both correct and incorrect; brief alert on wrong (no move reveal); manual mode only available in `mode=free` |
| 5 | Persistence | SQLite backend, sessions + attempts tables, "Sessões anteriores" list on config screen |
| 6 | Routing | `/` = config; `/play/:session_id` = session; `/play/:session_id/stats` = stats; `/explore` = current page |

## 3. Screen map

```
                    +----------------------+
                    |  /  (Configuracao)   |  porta de entrada
                    |                      |
                    |  Filtros + presets   |
                    |  Knobs da sessao     |
                    |  Buffer warming      |
                    |  Sessoes anteriores  |
                    |  [Iniciar]           |
                    +----------+-----------+
                               |
                  +------------v------------+
                  | POST /api/sessions      |
                  | -> session_id           |
                  +------------+------------+
                               |
          +--------------------v--------------------+
          |  /play/:session_id  (Sessao imersiva)   |
          |                                         |
          |  Tabuleiro grande                       |
          |  Cronometro                             |
          |  Contador correto/total                 |
          |  Botao discreto: encerrar agora         |
          |  (Modo livre) variant nav + free move   |
          +--------------------+--------------------+
                               | termino
                               v
          +-----------------------------------------+
          |  /play/:session_id/stats                |
          |                                         |
          |  Cards: total, corretos, tempo medio    |
          |  Histograma tempo x quantidade          |
          |  Scatter rating x tempo                 |
          |  Lista de errados + [Refazer errados]   |
          |  [Nova sessao]  [Voltar a configuracao] |
          +-----------------------------------------+

         /explore  (rota separada, ferramenta de curadoria)
         Tela atual movida sem alteracoes
         Acessivel por link discreto no header de /
```

## 4. Data model

Two new tables in the existing `puzzles.sqlite`:

```sql
CREATE TABLE sessions (
    session_id      TEXT PRIMARY KEY,
    started_at      TEXT NOT NULL,           -- ISO8601 UTC
    ended_at        TEXT,                    -- NULL while in progress
    end_reason      TEXT,                    -- 'time'|'count'|'manual'|NULL
    mode            TEXT NOT NULL,           -- 'time'|'count'|'free'
    target          INTEGER,                 -- minutes/puzzles; NULL in free
    auto_advance    INTEGER NOT NULL,        -- 0/1
    filters_json    TEXT NOT NULL,
    parent_session  TEXT,                    -- non-null when "redo failed"
    label           TEXT
);
CREATE INDEX idx_sessions_started ON sessions(started_at DESC);

CREATE TABLE attempts (
    session_id      TEXT NOT NULL,
    order_idx       INTEGER NOT NULL,
    puzzle_id       TEXT NOT NULL,
    correct         INTEGER NOT NULL,        -- 0/1
    time_ms         INTEGER NOT NULL,        -- USER_TURN -> first move
    completed_at    TEXT NOT NULL,
    PRIMARY KEY (session_id, order_idx),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
);
CREATE INDEX idx_attempts_session ON attempts(session_id);
CREATE INDEX idx_attempts_puzzle  ON attempts(puzzle_id);
```

### Conventions

- `time_ms` measures from the moment the board passes to the user (after the
  opponent's auto-played move) until the user begins their first move. Preview
  and opponent animation are excluded.
- `correct=0` means the user's first move was illegal or did not match the
  expected line (or, for mate puzzles, did not deliver checkmate). The actual
  wrong move is not stored; for "redo failed" only `puzzle_id` matters.
- `parent_session` allows tracing redo chains. If the user redoes and fails
  again, the new chain still points to the original.
- Aggregates (total correct, total time) are not stored — they are computed
  on the fly from `attempts` to avoid drift.
- Schema is created via `CREATE IF NOT EXISTS` in `app/db.py:init_db`. No
  migration tool required; the DB upgrade is purely additive.

## 5. HTTP API

### Existing (unchanged)

`GET /api/stats`, `GET /api/themes`, `GET /api/openings`,
`POST /api/puzzles/search`, `GET /api/puzzles/random`, `GET /api/puzzles/{id}`.

### New

```
GET /api/puzzles/batch?<filters>&limit=N
```
Returns up to N matching puzzles in random order. Implementation:
`SELECT * FROM puzzles WHERE <filters> ORDER BY RANDOM() LIMIT N`. Wide
filters (matching ~5M rows) cost ~1-2s; acceptable because this is invoked
once at the config -> session transition, not per-puzzle. Default N=500.

```
POST /api/sessions
body: {
  mode: "time"|"count"|"free",
  target: int|null,
  auto_advance: bool,
  dedupe_solved: bool,
  filters: {...},
  parent_session: string|null,
  label: string|null
}
-> 201 { session_id, started_at, pool_size }
```

`auto_advance` is forced to `true` server-side when `mode` is `time` or
`count`. Only in `mode=free` may the client send `auto_advance=false`, which
activates manual advance (single toggle covering both correct and wrong
outcomes, as described in section 7).
When `parent_session` is non-null, the backend ignores `filters` and builds the
pool from the `puzzle_id`s marked incorrect on the parent session.

```
POST /api/sessions/{id}/attempts
body: { order_idx, puzzle_id, correct, time_ms }
-> 204
```
Idempotent on `(session_id, order_idx)`. Returns 409 if the session has
`ended_at` set.

```
POST /api/sessions/{id}/end
body: { end_reason: "time"|"count"|"manual" }
-> 200 { ended_at, summary }
```

```
GET /api/sessions?limit=20&offset=0
-> [ { session_id, started_at, ended_at, mode, target, total, correct, label }, ... ]
```
Ordered by `started_at DESC`. Feeds the "Sessoes anteriores" list.

```
GET /api/sessions/{id}
-> {
  session: {...},
  attempts: [ { order_idx, puzzle_id, correct, time_ms, rating, themes }, ... ]
}
```
JOINs `puzzles` to bring `rating` and `themes` (needed by the scatter, by the
annotated histogram, and by the failed-puzzles list). Powers the deep-link to
`/play/:id/stats`.

### Idempotency and network failures

`POST attempts` is idempotent so the client can safely retry on transient
failure. The frontend never blocks UX on telemetry: if the POST fails, the
session continues and the client retries with exponential backoff. In the
worst case, one attempt is lost — the session state remains intact.

## 6. Trainer mechanics

### 6.1 Per-puzzle state machine

```
+--------------------------------------------------------+
| PREVIEW (300-500ms)                                    |
| - Render FEN from pool, with opponent to move          |
| - Orientation: side opposite to FEN side_to_move       |
|   (user sits behind the side that is about to receive  |
|    the opponent's move)                                |
| - Board inert (movable.color = null)                   |
| - Exercise clock not started                           |
+----------------------+---------------------------------+
                       |
                       v setTimeout 400ms
+--------------------------------------------------------+
| OPPONENT_MOVE (chess.js animation)                     |
| - Apply moves[0]                                       |
| - Board still inert                                    |
+----------------------+---------------------------------+
                       |
                       v animation 'after' callback
+--------------------------------------------------------+
| USER_TURN                                              |
| - movable.color set to the user's side                 |
| - Exercise clock starts                                |
| - Session clock continues uninterrupted                |
+--------------------------------------------------------+
```

Three states are necessary because the current prototype mixes them: it sets
`movable.color` immediately on FEN load and skips both PREVIEW and the visible
opponent move. Separating them in JS via `setTimeout` + chessground's `after`
animation callback fixes the bug.

### 6.2 Move validation

```
expectedUci = puzzle.moves[moveIndex]
isLastMove   = (moveIndex === puzzle.moves.length - 1)
isMatePuzzle = puzzle.themes.some(t => t.startsWith("mate"))

userUci = orig + dest + (promotion || "")
played  = chess.move({ from: orig, to: dest, promotion })

if (!played):
    return register_wrong_and_advance()       // illegal move = wrong

if (userUci === expectedUci):
    return continue_to_opponent_reply()

if (isLastMove && isMatePuzzle && chess.isCheckmate()):
    return register_correct()                 // alternative mate

chess.undo()
register_wrong_and_advance()
```

Done entirely client-side via chess.js. No Stockfish, no extra API call.
The `themes.startsWith("mate")` guard prevents accidental-mate moves from
being accepted in non-mate puzzles.

### 6.3 Fail-fast and internal marking

```
function register_wrong_and_advance():
    state.attempts.push({
        order_idx: state.attempts.length,
        puzzle_id: state.currentPuzzle.id,
        correct: false,
        time_ms: now() - state.exerciseStartedAt,
    })
    POST /api/sessions/{id}/attempts (non-blocking; retries in background)
    flash_alert(visual + audio)
    if (auto_advance) loadNextPuzzle() in ~300ms
    else show [Proximo] and [Tentar de novo]   // free mode only
```

The "internal marking" is simply `correct: false` in `state.attempts`.
"Redo failed" filters `state.attempts.filter(a => !a.correct).map(a => a.puzzle_id)`.

### 6.4 Multi-move puzzle flow on correct move

1. User's move is animated on the board.
2. `setTimeout 150ms` for visual breathing room.
3. Apply `moves[moveIndex+1]` (opponent's automatic reply).
4. `moveIndex += 2`.
5. If `moveIndex >= moves.length` -> puzzle solved -> `register_correct()`.
6. Else -> back to `USER_TURN`.

### 6.5 Error feedback

- Visual: subtle red border flash on the board (`animation: shake 200ms`).
- Audio: short clip (~150ms) at 50% volume default. Mute toggle in config.
- No success sound by default. May add later if requested.

## 7. Free mode features

When `mode=free`, the same load + validation flow applies. The user may
additionally set `auto_advance=false`, which is the only configuration
where the differences below appear; with `auto_advance=true`, free mode
behaves like time/count modes (no termination, but still auto-advancing
and with the same immersive layout).

### 7.1 Side panel (visible only when `mode=free` and `auto_advance=false`, after exercise outcome)

- **[Proximo exercicio]** — primary, always present.
- **[Tentar de novo]** — only if last was wrong. Rolls the board back to the
  post-`OPPONENT_MOVE` state and re-arms validation. Does not register a new
  attempt; the original wrong attempt is kept.
- **Variant navigation** — `[Inicio] [Anterior] [Proximo ▶] [Fim]` walking
  through the official solution moves. Implemented via `state.variantHistory`
  (FEN snapshots per move) + `state.variantCursor`. Keyboard shortcuts
  `Arrow Left` / `Arrow Right`.
- **Sandbox** — checkbox toggling `movable.color = 'both'` and
  `movable.free = true`. Local-only; does not touch attempts or solution
  state. Unticking restores variant position.

### 7.2 Clocks in free mode

- Exercise clock stops at the moment of outcome. `time_ms` reported is up to
  the user's first move, identical to other modes. Time spent exploring is
  ignored.
- Session clock keeps running while the session is open; it represents
  "wall-clock since session start", not "focused time".

### 7.3 Mode isolation

In `time` and `count` modes — and in `free` with `auto_advance=true` — the
side panel never appears. The trainer screen remains "absolute immersion" as
described: only board, clock, counter, and the discreet "encerrar agora"
button.

## 8. Screen layouts

### 8.1 `/` — Configuration

Two columns. Left column: filters (reuses 80% of current `static/js/filters.js`).
Right column: session knobs.

```
+----------------------------------------------------------------+
| lichess-puzzles                                  [/explore ↗]  |
+----------------------------------------------------------------+
|  +-- Filtros ----------------------+  +-- Sessao -----------+ |
|  | [Presets]                       |  | Modo:                | |
|  | -- Basico --                    |  | (o) Por tempo        | |
|  | Rating  [____] [____]           |  |     ( ) 3 ( ) 5 (10) | |
|  | Pecas   [____] [____]           |  |     ( ) outro [_] min| |
|  | Lance   [____] [____]           |  | ( ) Por quantidade   | |
|  | Popularity >= [____]            |  |     ( ) 50 (100) ... | |
|  | NbPlays    >= [____]            |  | ( ) Modo livre       | |
|  | -- Derivados / Themes / Open. --|  |                      | |
|  |                                 |  | [x] Remover resolvid.| |
|  | Encontrados: 12.834             |  | [ ] Som no erro      | |
|  +---------------------------------+  | (so modo livre):     | |
|                                       | [ ] Avanco manual    | |
|  [Buscar pool] -> ~1s spinner         |     (proximo lance e | |
|  Pool pronta: 487 puzzles             |      explorar livre) | |
|                                       +----------------------+ |
|  [Iniciar sessao]                                              |
|                                                                |
|  -- Sessoes anteriores ---------------------------------------|
|  29/abr 14:32 - time 5min  - 78/82  - "Mate em 2"   [→] [↻]  |
|  29/abr 13:10 - count 100  - 91/100 - "Sicilianas"  [→] [↻]  |
|  ...                                                           |
+----------------------------------------------------------------+
```

- "Buscar pool" calls `GET /api/puzzles/batch`. "Iniciar" enables when pool
  size >= 10. If pool < target, show "pool tem N puzzles, target ajustado
  para N" and clamp.
- Sessoes anteriores: last 20. `[→]` opens `/play/:id/stats`. `[↻]` issues a
  new `POST /api/sessions` reusing the same params and navigates.

### 8.2 `/play/:session_id` — Immersive session

```
+----------------------------------------------------------------+
|              ⏱  02:43         ✓ 47 / 50                        |
|                                                                |
|       +---------------------------------+                      |
|       |                                 |                      |
|       |       chessground board         |                      |
|       |       ~70vh, centered           |                      |
|       |                                 |                      |
|       +---------------------------------+                      |
|                                                                |
|                                                ⏹ encerrar      |
+----------------------------------------------------------------+
```

- No platform header. Dark neutral background.
- Clock top-center, ~3rem. In `time` it counts down (remaining); in `count`
  and `free` it counts up (elapsed).
- Counter: "✓ correct / target" in `count`; "✓ correct · ✗ wrong" in others.
- Encerrar button: opacity 0.4, hover -> 1.0. Confirms via modal to avoid
  accidental quit.
- Free mode: side panel from section 7.1 appears only after outcome.
- Keyboard: `Esc` = encerrar (with confirm), `n` = next (free), `r` = retry
  (free, after wrong).

### 8.3 `/play/:session_id/stats` — Stats

```
+----------------------------------------------------------------+
| Sessao 29/abr 15:14 — duracao 5:00 — 89/94 corretos       [✕] |
+----------------------------------------------------------------+
|  +-- Cards ------------------------------------------------+   |
|  | Total: 94 | Corretos: 89 | Erros: 5 | Medio: 3.2s       |   |
|  +---------------------------------------------------------+   |
|                                                                |
|  +-- Histograma de tempos --------------------------------+    |
|  | barras clicaveis -> popula lista filtrada abaixo       |    |
|  +--------------------------------------------------------+    |
|                                                                |
|  +-- Rating x tempo (scatter) ----------------------------+    |
|  | verde = correto, vermelho = errado                     |    |
|  +--------------------------------------------------------+    |
|                                                                |
|  -- Errados (5) ----  [Refazer todos os errados]               |
|  abc123 - 1840 - 8.2s  - #fork #endgame      [↗ Lichess]      |
|  ...                                                           |
|                                                                |
|  -- Lista filtrada (clicou na barra "8-10s") --                |
|  4 exercicios listados, com link para revisitar em /explore    |
|                                                                |
|  [Nova sessao (mesmos params)]   [Voltar a configuracao]       |
+----------------------------------------------------------------+
```

- Charts via uPlot (~40KB, MIT). Lighter than Chart.js, sufficient for both
  the histogram and the scatter.
- Histogram: 1s bins (configurable). Click on a bar populates the bottom
  "Lista filtrada".
- Scatter: each attempt is `(rating, time_ms)`; color by correct/wrong.
  Optional trend line via in-JS linear regression.
- Lista de errados: each row links to the Lichess game (`game_url`).
- "Refazer errados" creates a child session with `parent_session=this`.
- "Nova sessao" reuses the current session's `mode/target/filters`.
- "Voltar a configuracao" navigates to `/` with filters pre-filled from this
  session's `filters_json`.

## 9. Implementation phases

### Phase 1 — Persistent skeleton + routing

- Migration: `sessions` + `attempts` in `app/db.py`.
- Move current `/` to `/explore` (no logic changes).
- Stub `/` with empty config screen + empty "Sessoes anteriores".
- Endpoints: `POST /api/sessions`, `GET /api/sessions`,
  `GET /api/sessions/{id}`, `POST /api/sessions/{id}/end`,
  `POST /api/sessions/{id}/attempts`.
- Smoke: create session, post one fake attempt, end, list.
- Tests: integration over new routes with in-memory SQLite.

### Phase 2 — Correct trainer

- Endpoint `GET /api/puzzles/batch`.
- Refactor `static/js/trainer.js` around `PREVIEW -> OPPONENT_MOVE -> USER_TURN`.
- Fail-fast validation + mate-in-N alternative.
- Full config screen on `/` with knobs + "Buscar pool" + "Iniciar".
- `/play/:session_id` with clock + counter + board + encerrar (no stats yet).
- On end, redirect to `/explore` with placeholder.
- Manual smoke test: 3-min session, inspect attempts in DB.

### Phase 3 — Statistics screen

- Add uPlot to `static/vendor/`.
- Implement `/play/:session_id/stats`: cards + histogram + scatter + failed
  list + "Refazer errados".
- Wire `[Nova sessao]` and `[Voltar a configuracao]`.
- "Sessoes anteriores" on `/` becomes useful: `[→]` and `[↻]` work.

### Phase 4 — Free mode

- Add `mode=free` to config.
- Activate `auto_advance=false` path in session state (single toggle).
- Side panel: `[Proximo]`, `[Tentar de novo]`, variant nav, sandbox.
- Keyboard shortcuts.

### Phase 5 — Polish

- Error sound (`static/audio/error.mp3`).
- Confirm modal on `[encerrar]`.
- Pre-fill filters when "Voltar a configuracao".
- A11y: focus visible, ARIA roles, dark-mode contrast pass.

## 10. Dependencies and tests

### Dependencies

- Backend: none (uuid is stdlib).
- Frontend: uPlot (charts, ~40KB, MIT). Same convention as chessground:
  esm.sh in dev, vendored in `static/vendor/` for prod.
- Audio: one short `error.mp3` (~5KB).

### Tests (narrow, only what actually breaks)

- `test_sessions.py` — CRUD on sessions/attempts, idempotency of POST attempts,
  rejection on ended sessions, summary computation on `/end`.
- `test_batch.py` — `GET /api/puzzles/batch` respects limit and filters,
  produces different orderings across calls (flaky-tolerant assertion).
- `test_parent_session.py` — `parent_session` reuses incorrect puzzle_ids,
  ignores `filters` in the body.
- Frontend: no automated tests (continues current policy). Manual validation.

## 11. Risks and open questions

1. **Performance of `ORDER BY RANDOM() LIMIT 500` on broad filters.**
   Estimated 1-2s on ~5M rows; not measured. Plan B if too slow: pre-sample
   by `WHERE rowid % K = ?` for wide pools, accepting controlled loss of
   randomness.
2. **Animation race in OPPONENT_MOVE.** Chessground animates via `set({fen})`
   and `setMovable` must be deferred to the `after` animation callback, not
   `setTimeout` — otherwise the user can interact mid-animation.
3. **Mate-in-N "cooked" puzzles.** Some Lichess `mateIn2` puzzles include
   intermediate non-mate checks; only the last move is mate. The
   `themes.startsWith("mate") + isCheckmate() on last move` check is correct
   for these.
4. **Multi-tab.** Two tabs = two independent sessions. No sync needed.

## 12. Success criteria

1. `/` shows the config screen with filters, presets, session knobs, and the
   "Sessoes anteriores" list pulling from the backend.
2. Clicking "Iniciar" creates a session row, opens `/play/:id`, runs the
   `PREVIEW -> OPPONENT_MOVE -> USER_TURN` flow correctly on the first
   puzzle, and orientation matches the user's side.
3. Mate-in-1/2/3 puzzles accept any legal move that delivers checkmate as the
   final move; non-final moves are matched strictly against the solution.
4. A wrong move is registered as `correct=0`, the session continues, and at
   the end of the session, "Refazer errados" creates a child session with
   exactly those puzzle_ids.
5. The stats screen renders cards, histogram, and scatter from the attempts
   stored in SQLite, including via deep-link `/play/:id/stats` with no client
   memory of the session.
6. `/explore` continues to behave exactly as the current `/` does today.
