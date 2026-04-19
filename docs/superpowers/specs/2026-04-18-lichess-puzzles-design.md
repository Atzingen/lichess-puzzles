# lichess-puzzles — Design Spec

**Date:** 2026-04-18
**Author:** Gustavo von Atzingen
**Status:** Draft (awaiting user review)

## 1. Goal

Build a self-hosted web trainer that ingests the full Lichess puzzle database
(~5M puzzles) and exposes filtering capabilities beyond what lichess.org offers
out of the box. Users pick a filter (or preset), get a random puzzle that matches,
solve it on an interactive board, and rotate to the next one.

Two filters are explicitly not available on lichess.org that this app provides:

1. **Piece count on the board** (derived from FEN)
2. **Move number of the source game** (derived from FEN fullmove)

Plus every filter that comes for free from the dump (rating, popularity, themes,
opening, etc.) and a handful of cheap derived ones (side to move, phase,
material balance, flags for promoted/en-passant/castling).

## 2. Non-Goals (MVP)

- No user accounts, no login, no persistent history.
- No stats/tracking (success rate, streaks, ELO).
- No mobile-first design (desktop-first, mobile usable but not optimized).
- No favorites / bookmarks.
- No SSL / custom domain — direct IP + port access.

These may be revisited later; the design leaves room but does not implement them.

## 3. Architecture

Three clearly separated components:

```
+------------------+       +-----------------+       +----------------+
|   ingest/        |  -->  |   SQLite DB     |  <--  |   app/ (API)   |
|   (batch, once)  |       |   puzzles.sqlite|       |   FastAPI      |
+------------------+       +-----------------+       +----------------+
                                                              ^
                                                              |
                                                     +------------------+
                                                     |   static/ (UI)   |
                                                     |   HTML+chessgrd  |
                                                     +------------------+
```

- **ingest/** — one-shot Python CLI that downloads the official dump, streams
  it, computes derived columns, and bulk-inserts into SQLite.
- **app/** — FastAPI server. Reads SQLite, exposes JSON API, serves static UI.
- **static/** — plain HTML + CSS + JS (no framework). Uses `chessground` for
  the visual board and `chess.js` for move validation.

Deployment: single Docker container on `hostinger-02`, port `8004`, accessed
via `http://72.61.43.231:8004`.

## 4. Data Source

Official Lichess dump: `https://database.lichess.org/lichess_db_puzzle.csv.zst`

CSV columns (from the dump):
`PuzzleId, FEN, Moves, Rating, RatingDeviation, Popularity, NbPlays, Themes,
GameUrl, OpeningTags`

Size: ~800 MB compressed, ~5M rows. Updated roughly monthly by Lichess.

## 5. SQLite Schema

```sql
CREATE TABLE puzzles (
    puzzle_id          TEXT PRIMARY KEY,
    fen                TEXT NOT NULL,
    moves              TEXT NOT NULL,            -- UCI moves, space-separated
    rating             INTEGER NOT NULL,
    rating_deviation   INTEGER NOT NULL,
    popularity         INTEGER NOT NULL,
    nb_plays           INTEGER NOT NULL,
    themes             TEXT NOT NULL,            -- space-separated (kept for display)
    game_url           TEXT,
    opening_tags       TEXT,                     -- space-separated, nullable

    -- Derived in ingest
    piece_count        INTEGER NOT NULL,         -- total pieces on board
    move_number        INTEGER NOT NULL,         -- FEN fullmove
    side_to_move       TEXT NOT NULL,            -- 'w' | 'b'
    phase              TEXT NOT NULL,            -- 'opening' | 'middlegame' | 'endgame'
    material_balance   INTEGER NOT NULL,         -- white_value - black_value
    has_promoted       INTEGER NOT NULL,         -- 0/1
    has_en_passant     INTEGER NOT NULL,         -- 0/1
    castling_rights    TEXT NOT NULL             -- 'KQkq', '-', etc.
);

CREATE INDEX idx_rating        ON puzzles(rating);
CREATE INDEX idx_piece_count   ON puzzles(piece_count);
CREATE INDEX idx_move_number   ON puzzles(move_number);
CREATE INDEX idx_phase         ON puzzles(phase);
CREATE INDEX idx_side          ON puzzles(side_to_move);
CREATE INDEX idx_popularity    ON puzzles(popularity);

CREATE TABLE puzzle_themes (
    puzzle_id  TEXT NOT NULL,
    theme      TEXT NOT NULL,
    PRIMARY KEY (puzzle_id, theme)
);
CREATE INDEX idx_theme ON puzzle_themes(theme);
```

### Derivation rules

- `piece_count`: count of non-digit, non-`/` chars in the FEN board segment.
- `move_number`: integer at position 5 of the FEN (fullmove counter).
- `side_to_move`: char at position 1 of the FEN (`w` or `b`).
- `phase`:
  - `opening` if `move_number <= 10`
  - `endgame` if `piece_count <= 10`
  - `middlegame` otherwise
- `material_balance`: sum of piece values (P=1, N=3, B=3, R=5, Q=9) for white
  minus the same for black.
- `has_promoted`: true if any piece type exceeds its initial count (e.g., 3
  knights, 2 queens on the same side).
- `has_en_passant`: true if FEN en-passant target square is not `-`.
- `castling_rights`: raw FEN castling field (`KQkq`, `Kq`, `-`, etc.).

## 6. Ingest Pipeline

`ingest/run.py`:

1. If `data/lichess_db_puzzle.csv.zst` exists and is < 30 days old, reuse it;
   otherwise download.
2. Open with `zstandard.ZstdDecompressor().stream_reader(...)` + `csv.DictReader`
   over a `io.TextIOWrapper` — streaming, no full decompression on disk.
3. For each row, use `python-chess` (`chess.Board.from_fen`) to compute derived
   columns.
4. Bulk-insert into SQLite in batches of 10 000, inside a single transaction,
   with `PRAGMA synchronous=OFF`, `PRAGMA journal_mode=MEMORY`.
5. Create indexes at the end (faster than incremental).
6. `VACUUM` + `ANALYZE`.
7. Progress bar via `tqdm`.

Expected runtime on modern hardware: 5-10 minutes end-to-end.
Final DB size: ~2-3 GB.

## 7. API (FastAPI)

```
GET  /                         serve index.html
GET  /static/*                 static assets

GET  /api/stats                { total_puzzles, rating_range, piece_count_range }
GET  /api/themes               list of distinct themes (for UI selects)
GET  /api/openings             list of distinct opening tags

POST /api/puzzles/search       body: filters -> { count: N, sample_ids: [...5] }
GET  /api/puzzles/random       query: filters -> one random puzzle (or null)
GET  /api/puzzles/{id}         lookup by ID (for deep-linking / debugging)
```

### Filter schema (all optional)

```json
{
  "rating_min": 1500, "rating_max": 2000,
  "piece_count_min": 4, "piece_count_max": 12,
  "move_number_min": 15, "move_number_max": null,
  "popularity_min": 50,
  "nb_plays_min": 100,
  "themes_any":  ["fork", "pin"],
  "themes_all":  ["endgame", "mate"],
  "opening_tags_any": ["Sicilian_Defense"],
  "side_to_move": "w",
  "phase": "endgame",
  "material_balance_min": -3, "material_balance_max": 3,
  "has_promoted": false,
  "has_en_passant": null,
  "has_castling": null
}
```

### Random sampling strategy

1. `SELECT COUNT(*) FROM puzzles <JOINs> WHERE <filters>` → N
2. If N = 0: return `{count: 0, puzzle: null}`
3. Pick `offset = random.randrange(N)`
4. `SELECT * FROM puzzles <JOINs> WHERE <filters> LIMIT 1 OFFSET offset`

Two small queries, both index-backed. Correct uniformity and handles empty
results cleanly. The classic `ORDER BY RANDOM() LIMIT 1` is avoided (slow on 5M
rows).

### Filter composition rules

- All range filters translate to `AND col BETWEEN ? AND ?` (or one-sided if
  null).
- `themes_any`: `puzzle_id IN (SELECT puzzle_id FROM puzzle_themes WHERE theme IN (...))`.
- `themes_all`: `puzzle_id IN (SELECT puzzle_id FROM puzzle_themes WHERE theme IN (...) GROUP BY puzzle_id HAVING COUNT(DISTINCT theme) = N)`.
- `opening_tags_any`: LIKE match against the space-separated `opening_tags`
  column (small set per row, no separate table needed).

All filter values bind via `?` placeholders — no string interpolation.

## 8. Frontend

Plain HTML + CSS + JS, no bundler. Dependencies from `static/vendor/`:

- `chessground` — visual board (same library lichess.org uses)
- `chess.js` — move legality + game state

### Layout (desktop, 3 columns)

```
+-----------------------------------------------------------------+
| HEADER: lichess-puzzles  |  N filtered: 12,384  |  puzzle info  |
+------------------+------------------+---------------------------+
|  FILTERS         |     BOARD        |    PUZZLE INFO            |
|  (accordions)    |   chessground    |    ID, rating, themes,    |
|                  |                  |    opening, link to lichess|
|  Basic           |                  |                           |
|  Derived         |                  |  [Reveal] [Reset] [Next]  |
|  Themes          |                  |                           |
|  Openings        |                  |                           |
|                  |                  |                           |
|  [Search]        |                  |                           |
+------------------+------------------+---------------------------+
```

Mobile: columns stack. Filters collapse into a drawer.

### Trainer flow

1. Page load: `GET /api/stats`, `/api/themes`, `/api/openings` populate controls.
2. Filter change: debounced (300ms) `POST /api/puzzles/search` → update "N filtered" counter.
3. Click **Search** (or pick a preset): `GET /api/puzzles/random?<filters>` → first puzzle.
4. Frontend loads FEN into `chessground`, locks the board to the side to move.
5. User drags a piece → `chess.js` validates legality → compared against
   `moves[current_index]`:
   - **Correct move**: piece moves, opponent's reply auto-plays after 500ms
     (if any), `current_index` advances. If last move → "Solved ✓" → auto-load
     next puzzle after 1.5s.
   - **Wrong move**: undo, flash "Try again ✗" for 1s.
6. **Reveal**: animate through the solution with arrows.
7. **Next**: `GET /api/puzzles/random?<same filters>` — frontend keeps a
   short-term "last 10 seen" list and re-rolls if server returns a repeat.
8. **Reset**: reload the current puzzle's starting FEN.

### State

Single plain object:
```js
const state = {
  filters,            // current filter values
  currentPuzzle,      // { id, fen, moves, ... }
  currentMoveIndex,   // how many of the solution moves played
  recentIds,          // last 10 seen IDs
  board,              // chessground instance
  game                // chess.js instance
};
```

### File layout

```
static/
  index.html
  presets.json
  css/styles.css
  js/
    api.js
    filters.js
    trainer.js
    ui.js
    main.js
  vendor/
    chessground.min.js
    chess.min.js
    chessground.css
```

## 9. Presets

Shown as a row of quick-filter buttons at the top of the filter panel. Clicking
a preset fills the filter form and triggers an immediate search. Stored in
`static/presets.json` for easy editing.

| Preset | Filters |
|---|---|
| Finais básicos | `piece_count 4-8`, `phase=endgame`, `rating 1000-1400` |
| Mate em 1 | `themes_all=[mate, mateIn1]` |
| Mate em 2 | `themes_all=[mate, mateIn2]` |
| Mate em 3 | `themes_all=[mate, mateIn3]` |
| Táticas clássicas | `phase=middlegame`, `rating 1500-1900`, `themes_any=[fork, pin, skewer, discoveredAttack]` |
| Sacrifícios posicionais | `themes_all=[sacrifice]`, `rating_min=1800` |
| Siciliana | `opening_tags_any=[Sicilian_Defense]`, `move_number 10-20` |
| Finais de torre | `phase=endgame`, `themes_any=[rookEndgame]` |
| Populares | `popularity_min=80`, `nb_plays_min=1000` |
| Desafio alto | `rating 2000-2400`, `popularity_min=50` |

## 10. Repository Structure

```
lichess-puzzles/
├── README.md
├── LICENSE                         # MIT
├── .gitignore
├── .dockerignore
├── pyproject.toml
├── Makefile
├── Dockerfile
├── docker-compose.yml
├── .env.example
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   ├── filters.py
│   ├── models.py
│   └── routers/
│       ├── puzzles.py
│       └── meta.py
│
├── ingest/
│   ├── __init__.py
│   ├── download.py
│   ├── derive.py
│   └── run.py
│
├── static/
│   ├── index.html
│   ├── presets.json
│   ├── css/styles.css
│   ├── js/{api,filters,trainer,ui,main}.js
│   └── vendor/
│
├── tests/
│   ├── conftest.py
│   ├── test_filters.py
│   ├── test_derive.py
│   ├── test_api.py
│   └── fixtures/
│       └── puzzles_sample.csv
│
├── data/                           # gitignored; mounted as volume
│   └── .gitkeep
│
├── docs/
│   └── superpowers/specs/
│       └── 2026-04-18-lichess-puzzles-design.md
│
└── .github/
    └── workflows/
        └── deploy.yml
```

## 11. Docker

**Dockerfile** (multi-stage slim):
```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl build-essential && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
RUN pip install --no-cache-dir .
COPY app/ ./app/
COPY ingest/ ./ingest/
COPY static/ ./static/
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**docker-compose.yml:**
```yaml
services:
  app:
    build: .
    container_name: lichess-puzzles
    ports:
      - "8004:8000"
    volumes:
      - ./data:/app/data
    environment:
      - DB_PATH=/app/data/puzzles.sqlite
    restart: unless-stopped
```

**Makefile targets:**
- `make build` — build image
- `make up` / `make down` — start/stop
- `make logs` — tail logs
- `make ingest` — run `docker compose run --rm app python -m ingest.run`
- `make rebuild` — down + build + up
- `make test` — run pytest inside the image

## 12. CI/CD — GitHub Actions

File: `.github/workflows/deploy.yml`

- Trigger: push to `main`
- Job `test`: `pip install .[dev]`, `pytest`
- Job `deploy` (needs: test): SSH into `deployer@72.61.43.231`, `cd /var/local/apps/lichess-puzzles && git pull && make rebuild`

Repo secrets:
- `SSH_HOST_HOSTINGER02` = `72.61.43.231`
- `SSH_USER_HOSTINGER02` = `deployer`
- `SSH_PRIVATE_KEY_HOSTINGER02` = private key matching a deploy key on the server

## 13. First Deploy (manual, one-shot)

On `hostinger-02` as `deployer`:

```bash
mkdir -p /var/local/apps/lichess-puzzles
cd /var/local/apps/lichess-puzzles
ssh-keygen -t ed25519 -f ~/.ssh/lichess_puzzles_deploy_key -N ""
# add pubkey as a Deploy Key on GitHub repo (read-only)
GIT_SSH_COMMAND='ssh -i ~/.ssh/lichess_puzzles_deploy_key' \
  git clone git@github.com:Atzingen/lichess-puzzles.git .
make build
make ingest           # ~10 min, one-time
make up
# open http://72.61.43.231:8004
```

Confirm port 8004 is open to WAN on `hostinger-02` (pfSense / provider firewall).

## 14. Testing

Scope is narrow — only things that actually break:

- **`test_derive.py`** — derived-column calculation on handcrafted FENs
  (starting position, bare kings, symmetric, promoted pieces, en passant).
- **`test_filters.py`** — `build_where()` produces the right SQL + params for
  each filter shape and combination.
- **`test_api.py`** — integration against a SQLite fixture populated with
  ~100 puzzles (`tests/fixtures/puzzles_sample.csv`). Covers: search counts,
  random-within-filter, empty-result handling, 404 on bad id.

Out of scope: browser UI automation, real dump download, full 5M ingest
performance. Those are verified manually.

Tools: `pytest`, `httpx.AsyncClient`. CI runs these before allowing deploy.

## 15. Open Questions / Future Work

- **Persistence (post-MVP)**: `localStorage` for solved-history and favorites
  (no server state, no login).
- **Domain + SSL (post-MVP)**: nginx reverse proxy with certbot, if a domain
  is desired later.
- **Monthly dump refresh**: could be automated via a cron that runs
  `make ingest` on the 1st of each month.
- **More derived columns**: e.g., "has a check", "two-bishop endgame flag",
  if the community or user requests them.
- **Preset editor UI**: for now, presets are hand-edited in `presets.json`.

## 16. Success Criteria (MVP)

1. `make ingest` completes successfully on the full Lichess dump in under
   15 minutes and produces a DB with > 4M puzzles.
2. All filter combinations return results in < 200ms on `hostinger-02`.
3. A random puzzle loads into the board and can be solved interactively, with
   correct validation of every solution move.
4. `Next` rotates to a fresh puzzle within the same filter and never repeats
   within the last 10.
5. All 10 preset buttons work end-to-end.
6. GitHub Actions deploy on push to `main` succeeds and the app updates on the
   server without manual intervention (aside from the very first bootstrap).
