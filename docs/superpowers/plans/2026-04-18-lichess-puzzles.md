# lichess-puzzles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest the full Lichess puzzle dump into SQLite and serve a FastAPI + chessground trainer with richer filters than lichess.org (including piece-count and move-number filters), deployed to `hostinger-02:8004`.

**Architecture:** Three clearly separated components — one-shot Python ingest that streams the zstd-compressed dump and computes derived columns with python-chess, a FastAPI server that builds parameterised SQL from filter objects, and a vanilla HTML/JS frontend that uses chessground + chess.js for board rendering and move validation. Docker-compose on one container, GitHub Actions deploy.

**Tech Stack:** Python 3.12, FastAPI, SQLite, python-chess, zstandard, pydantic v2, pytest, httpx, chessground, chess.js, Docker, GitHub Actions.

**Working directory for all tasks:** `C:\Users\Gustavo\Desktop\dev\lichess-puzzles` (already git-inited with the design spec committed on `main`).

**Success = all 23 tasks complete + app reachable at `http://72.61.43.231:8004` with working filters and rotation.**

---

## Task 1: Create GitHub repo and push initial commit

**Files:** none new — uses existing git repo.

- [ ] **Step 1: Verify `gh` is authenticated as Atzingen**

Run: `gh auth status`
Expected: shows `Logged in to github.com as Atzingen` (or similar). If not, run `gh auth login` and log in as the personal account.

- [ ] **Step 2: Create the public GitHub repo under the Atzingen account**

Run:
```bash
cd /c/Users/Gustavo/Desktop/dev/lichess-puzzles
gh repo create Atzingen/lichess-puzzles \
  --public \
  --description "Self-hosted Lichess puzzle trainer with richer filters (piece count, move number) than lichess.org" \
  --source . \
  --remote origin \
  --push
```
Expected: remote added, existing `main` branch pushed. `gh repo view Atzingen/lichess-puzzles --web` opens the new repo.

- [ ] **Step 3: Verify remote**

Run: `git remote -v`
Expected: `origin  git@github.com:Atzingen/lichess-puzzles.git (fetch|push)`

---

## Task 2: Python project skeleton (pyproject.toml, folders, .dockerignore)

**Files:**
- Create: `pyproject.toml`
- Create: `.dockerignore`
- Create: `.env.example`
- Create: `app/__init__.py` `app/routers/__init__.py`
- Create: `ingest/__init__.py`
- Create: `tests/__init__.py` `tests/fixtures/.gitkeep`
- Create: `static/.gitkeep`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "lichess-puzzles"
version = "0.1.0"
description = "Self-hosted Lichess puzzle trainer with extended filters"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    "python-chess>=1.999",
    "zstandard>=0.22",
    "httpx>=0.27",
    "tqdm>=4.66",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",
]

[tool.setuptools.packages.find]
include = ["app*", "ingest*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Write `.dockerignore`**

```
.git
.github
.venv
venv
__pycache__
*.pyc
.pytest_cache
data/*.sqtest-fixtures
data/*.csv.zst
data/*.sqlite
docs
tests
.env
.env.local
```

- [ ] **Step 3: Write `.env.example`**

```
DB_PATH=./data/puzzles.sqlite
DUMP_URL=https://database.lichess.org/lichess_db_puzzle.csv.zst
DUMP_PATH=./data/lichess_db_puzzle.csv.zst
```

- [ ] **Step 4: Create empty package files**

Create empty files at: `app/__init__.py`, `app/routers/__init__.py`, `ingest/__init__.py`, `tests/__init__.py`, `tests/fixtures/.gitkeep`, `static/.gitkeep`.

- [ ] **Step 5: Create `.venv` and install**

Run:
```bash
python -m venv .venv
source .venv/Scripts/activate  # Git Bash on Windows
pip install -e ".[dev]"
```
Expected: all dependencies install, package installable in editable mode.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .dockerignore .env.example app/ ingest/ tests/ static/
git commit -m "chore: Python project skeleton with pyproject.toml and packages"
```

---

## Task 3: Settings module

**Files:**
- Create: `app/config.py`

- [ ] **Step 1: Write `app/config.py`**

```python
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_path: Path = Path("./data/puzzles.sqlite")
    dump_url: str = "https://database.lichess.org/lichess_db_puzzle.csv.zst"
    dump_path: Path = Path("./data/lichess_db_puzzle.csv.zst")


settings = Settings()
```

- [ ] **Step 2: Smoke-test import**

Run: `python -c "from app.config import settings; print(settings.db_path)"`
Expected: prints the default path without errors.

- [ ] **Step 3: Commit**

```bash
git add app/config.py
git commit -m "feat(config): add pydantic settings module"
```

---

## Task 4: Database schema and connection helper (TDD)

**Files:**
- Create: `app/db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write failing test `tests/test_db.py`**

```python
import sqlite3
from pathlib import Path

from app.db import init_db, connect


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
    for needed in [
        "idx_rating", "idx_piece_count", "idx_move_number",
        "idx_phase", "idx_side", "idx_popularity", "idx_theme",
    ]:
        assert needed in indexes, f"missing index {needed}"


def test_connect_returns_row_factory(tmp_path: Path) -> None:
    db_path = tmp_path / "t.sqlite"
    init_db(db_path)
    conn = connect(db_path)
    try:
        row = conn.execute("SELECT 1 AS one").fetchone()
        assert row["one"] == 1
    finally:
        conn.close()
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_db.py -v`
Expected: ImportError / ModuleNotFoundError for `app.db`.

- [ ] **Step 3: Write `app/db.py`**

```python
import sqlite3
from pathlib import Path

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
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_rating        ON puzzles(rating)",
    "CREATE INDEX IF NOT EXISTS idx_piece_count   ON puzzles(piece_count)",
    "CREATE INDEX IF NOT EXISTS idx_move_number   ON puzzles(move_number)",
    "CREATE INDEX IF NOT EXISTS idx_phase         ON puzzles(phase)",
    "CREATE INDEX IF NOT EXISTS idx_side          ON puzzles(side_to_move)",
    "CREATE INDEX IF NOT EXISTS idx_popularity    ON puzzles(popularity)",
    "CREATE INDEX IF NOT EXISTS idx_theme         ON puzzle_themes(theme)",
]


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        for stmt in INDEXES:
            conn.execute(stmt)
        conn.commit()
    finally:
        conn.close()


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
```

- [ ] **Step 4: Run tests — expect green**

Run: `pytest tests/test_db.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app/db.py tests/test_db.py
git commit -m "feat(db): SQLite schema init and row-factory connect helper"
```

---

## Task 5: FEN derivation utilities (TDD)

**Files:**
- Create: `ingest/derive.py`
- Create: `tests/test_derive.py`

- [ ] **Step 1: Write `tests/test_derive.py`**

```python
from ingest.derive import derive_columns, PIECE_VALUES

STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
BARE_KINGS = "4k3/8/8/8/8/8/8/4K3 w - - 0 1"
ENDGAME_ROOKS = "4k3/8/8/8/8/8/R7/4K3 w - - 10 50"
WHITE_DOWN_QUEEN = "rnb1kbnr/pppppppp/8/8/8/8/PPPPPPPP/RNB1KBNR w KQkq - 0 1"  # white no queen
EP_AVAILABLE = "rnbqkbnr/ppp1pppp/8/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 3"
PROMOTED_3_KNIGHTS = "4k3/8/8/8/8/8/NN1N4/4K3 w - - 20 40"
NO_CASTLING = "4k3/8/8/8/8/8/8/4K3 w - - 0 1"


def test_piece_count_starting_position():
    assert derive_columns(STARTING_FEN)["piece_count"] == 32


def test_piece_count_bare_kings():
    assert derive_columns(BARE_KINGS)["piece_count"] == 2


def test_side_to_move():
    assert derive_columns(STARTING_FEN)["side_to_move"] == "w"
    assert derive_columns("4k3/8/8/8/8/8/8/4K3 b - - 0 1")["side_to_move"] == "b"


def test_move_number():
    assert derive_columns(STARTING_FEN)["move_number"] == 1
    assert derive_columns(ENDGAME_ROOKS)["move_number"] == 50


def test_phase_precedence_opening_wins():
    cols = derive_columns(STARTING_FEN)
    assert cols["phase"] == "opening"


def test_phase_endgame_when_move_above_10_and_few_pieces():
    cols = derive_columns(ENDGAME_ROOKS)
    assert cols["phase"] == "endgame"


def test_phase_middlegame():
    fen = "r1bqkb1r/pppp1ppp/2n2n2/4p3/4P3/2N2N2/PPPP1PPP/R1BQKB1R w KQkq - 4 11"
    cols = derive_columns(fen)
    assert cols["phase"] == "middlegame"


def test_material_balance_symmetric():
    assert derive_columns(STARTING_FEN)["material_balance"] == 0


def test_material_balance_white_down_queen():
    assert derive_columns(WHITE_DOWN_QUEEN)["material_balance"] == -PIECE_VALUES["q"]


def test_has_en_passant():
    assert derive_columns(STARTING_FEN)["has_en_passant"] == 0
    assert derive_columns(EP_AVAILABLE)["has_en_passant"] == 1


def test_castling_rights_raw():
    assert derive_columns(STARTING_FEN)["castling_rights"] == "KQkq"
    assert derive_columns(NO_CASTLING)["castling_rights"] == "-"


def test_has_promoted_three_knights():
    assert derive_columns(PROMOTED_3_KNIGHTS)["has_promoted"] == 1


def test_has_not_promoted_in_starting_position():
    assert derive_columns(STARTING_FEN)["has_promoted"] == 0
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/test_derive.py -v`
Expected: ImportError for `ingest.derive`.

- [ ] **Step 3: Write `ingest/derive.py`**

```python
from __future__ import annotations

PIECE_VALUES: dict[str, int] = {
    "p": 1, "n": 3, "b": 3, "r": 5, "q": 9, "k": 0
}

INITIAL_MAX: dict[str, int] = {
    # per-side maxima in the starting position
    "p": 8, "n": 2, "b": 2, "r": 2, "q": 1, "k": 1,
}


def _parse_fen(fen: str) -> tuple[str, str, str, str, int, int]:
    parts = fen.strip().split()
    if len(parts) < 6:
        raise ValueError(f"malformed FEN: {fen!r}")
    board, side, castling, ep, halfmove, fullmove = parts[:6]
    return board, side, castling, ep, int(halfmove), int(fullmove)


def _count_pieces(board: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ch in board:
        if ch.isalpha():
            counts[ch] = counts.get(ch, 0) + 1
    return counts


def _material_balance(counts: dict[str, int]) -> int:
    white = sum(PIECE_VALUES[k.lower()] * v for k, v in counts.items() if k.isupper())
    black = sum(PIECE_VALUES[k] * v for k, v in counts.items() if k.islower())
    return white - black


def _has_promoted(counts: dict[str, int]) -> bool:
    for piece, max_count in INITIAL_MAX.items():
        if counts.get(piece.upper(), 0) > max_count:
            return True
        if counts.get(piece, 0) > max_count:
            return True
    return False


def derive_columns(fen: str) -> dict[str, object]:
    board, side, castling, ep, _halfmove, fullmove = _parse_fen(fen)
    counts = _count_pieces(board)
    piece_count = sum(counts.values())

    if fullmove <= 10:
        phase = "opening"
    elif piece_count <= 10:
        phase = "endgame"
    else:
        phase = "middlegame"

    return {
        "piece_count": piece_count,
        "move_number": fullmove,
        "side_to_move": side,
        "phase": phase,
        "material_balance": _material_balance(counts),
        "has_promoted": 1 if _has_promoted(counts) else 0,
        "has_en_passant": 0 if ep == "-" else 1,
        "castling_rights": castling,
    }
```

- [ ] **Step 4: Run tests — expect green**

Run: `pytest tests/test_derive.py -v`
Expected: 13 passed.

- [ ] **Step 5: Commit**

```bash
git add ingest/derive.py tests/test_derive.py
git commit -m "feat(ingest): FEN derivation utilities with full test coverage"
```

---

## Task 6: Fixture CSV for ingest + API tests

**Files:**
- Create: `tests/fixtures/puzzles_sample.csv`

- [ ] **Step 1: Write a 10-line fixture CSV at `tests/fixtures/puzzles_sample.csv`**

```
PuzzleId,FEN,Moves,Rating,RatingDeviation,Popularity,NbPlays,Themes,GameUrl,OpeningTags
00008,r6k/pp2r2p/4Rp1Q/3p4/8/1N1P2R1/PqP2bPP/7K b - - 0 24,f2g3 e6e7 b2b1 b3c1 b1c1 h6c1,1812,75,97,3152,advantage attraction fork middlegame short,https://lichess.org/yyznGmXs/black#48,Kings_Gambit_Accepted Kings_Gambit_Accepted_Abbazia_Defense
0000D,5rk1/1p3ppp/pq3b2/8/8/1P1Q1N2/P4PPP/3R2K1 w - - 2 23,d3d6 f8d8 d6d8 f6d8,1556,75,94,8216,advantage endgame short,https://lichess.org/F8M8OS71/white#45,
0009B,r1bq1rk1/pp3pbp/2n1pnp1/2pp4/3P4/2PBPN1P/PP1N1PP1/R1BQR1K1 b - - 0 9,c5d4 c3d4 c6b4 d3b1,1261,74,96,1243,advantage middlegame short,https://lichess.org/FKaqnt4A/black#18,
0009R,3r1rk1/p4p1p/1p4p1/2pP4/8/1NP5/PP3PPP/R4RK1 w - - 0 22,d5d6 a7a6 d6d7 f8d8 a1d1 d8d7,1522,75,87,1012,advantage endgame long,https://lichess.org/Xg5cGM9Z/white#43,
000Vs,8/8/4k3/5q2/5P2/8/6K1/8 b - - 1 60,f5g4 g2h2 g4h4,952,74,93,4021,endgame mate mateIn2 short,https://lichess.org/4MWQvU61/black#119,
001AD,r1b1kb1r/pp1n1ppp/2p1pn2/6B1/2pP4/2N1PN2/PP3PPP/R2QKB1R w KQkq - 0 8,g5f6 d7f6 f1c4 b7b5 c4b5 c6b5 c3b5,1389,75,89,992,advantage middlegame short,https://lichess.org/jXaJAoL3/white#15,
001AE,r2qkb1r/ppp2pp1/2np1n1p/8/3PP3/2N5/PPP1BPPP/R1BQK2R b KQkq - 0 8,c8g4 e2g4 f6g4,1024,76,91,2188,advantage middlegame short,https://lichess.org/jXaJAoL4/black#16,Scandinavian_Defense
001AF,8/8/8/8/4k3/8/R7/4K3 w - - 0 50,a2a4 e4f5 a4a5 f5e6 a5a6,1600,80,78,540,endgame mate mateIn3,https://lichess.org/game50/white#99,
001AG,6k1/5ppp/8/8/8/8/5PPP/6K1 w - - 0 40,g1f1 g8g7 f1e2 g7f6 e2e3,1100,80,80,300,endgame middlegame,https://lichess.org/game51/white#79,
001AH,r2qkb1r/ppp2ppp/2np1n2/1B2p1B1/4P3/2N2N2/PPP2PPP/R2QK2R w KQkq - 0 7,g5f6 g7f6 b5c6 b7c6 f3e5 f6e5,1725,75,92,1500,advantage middlegame short,https://lichess.org/game70/white#13,Ruy_Lopez_Exchange_Variation
```

- [ ] **Step 2: Sanity-check readable**

Run: `python -c "import csv; r=list(csv.DictReader(open('tests/fixtures/puzzles_sample.csv'))); print(len(r), r[0]['PuzzleId'])"`
Expected: `10 00008`

- [ ] **Step 3: Commit**

```bash
git add tests/fixtures/puzzles_sample.csv
git commit -m "test: 10-puzzle fixture CSV for ingest and API tests"
```

---

## Task 7: Ingest writer — insert a row dict into SQLite (TDD)

**Files:**
- Create: `ingest/writer.py`
- Create: `tests/test_writer.py`

- [ ] **Step 1: Write `tests/test_writer.py`**

```python
import sqlite3
from pathlib import Path

from app.db import init_db
from ingest.writer import insert_batch, row_from_csv


def _csv_row() -> dict[str, str]:
    return {
        "PuzzleId": "ABC12",
        "FEN": "4k3/8/8/8/8/8/R7/4K3 w - - 10 50",
        "Moves": "a2a4 e4f5",
        "Rating": "1600",
        "RatingDeviation": "80",
        "Popularity": "90",
        "NbPlays": "500",
        "Themes": "endgame mate",
        "GameUrl": "https://lichess.org/x",
        "OpeningTags": "",
    }


def test_row_from_csv_computes_derived(tmp_path: Path) -> None:
    row, themes = row_from_csv(_csv_row())
    assert row["puzzle_id"] == "ABC12"
    assert row["piece_count"] == 3
    assert row["move_number"] == 50
    assert row["phase"] == "endgame"
    assert row["side_to_move"] == "w"
    assert themes == ["endgame", "mate"]


def test_insert_batch_writes_and_joins(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    init_db(db)
    rows = [row_from_csv(_csv_row())]
    conn = sqlite3.connect(db)
    try:
        insert_batch(conn, rows)
        conn.commit()
        got = conn.execute("SELECT piece_count, phase FROM puzzles").fetchone()
        themes = [r[0] for r in conn.execute(
            "SELECT theme FROM puzzle_themes WHERE puzzle_id=?", ("ABC12",)
        )]
    finally:
        conn.close()
    assert got == (3, "endgame")
    assert sorted(themes) == ["endgame", "mate"]
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/test_writer.py -v`
Expected: ModuleNotFoundError for `ingest.writer`.

- [ ] **Step 3: Write `ingest/writer.py`**

```python
from __future__ import annotations

import sqlite3
from typing import Iterable

from ingest.derive import derive_columns


COLUMNS = [
    "puzzle_id", "fen", "moves", "rating", "rating_deviation",
    "popularity", "nb_plays", "themes", "game_url", "opening_tags",
    "piece_count", "move_number", "side_to_move", "phase",
    "material_balance", "has_promoted", "has_en_passant", "castling_rights",
]
INSERT_SQL = (
    f"INSERT OR REPLACE INTO puzzles ({', '.join(COLUMNS)}) "
    f"VALUES ({', '.join('?' * len(COLUMNS))})"
)
INSERT_THEME_SQL = (
    "INSERT OR IGNORE INTO puzzle_themes (puzzle_id, theme) VALUES (?, ?)"
)


def row_from_csv(csv_row: dict[str, str]) -> tuple[dict[str, object], list[str]]:
    derived = derive_columns(csv_row["FEN"])
    themes_raw = (csv_row.get("Themes") or "").strip()
    themes_list = themes_raw.split() if themes_raw else []
    row = {
        "puzzle_id": csv_row["PuzzleId"],
        "fen": csv_row["FEN"],
        "moves": csv_row["Moves"],
        "rating": int(csv_row["Rating"]),
        "rating_deviation": int(csv_row["RatingDeviation"]),
        "popularity": int(csv_row["Popularity"]),
        "nb_plays": int(csv_row["NbPlays"]),
        "themes": themes_raw,
        "game_url": csv_row.get("GameUrl") or None,
        "opening_tags": (csv_row.get("OpeningTags") or None) or None,
        **derived,
    }
    return row, themes_list


def insert_batch(
    conn: sqlite3.Connection,
    batch: Iterable[tuple[dict[str, object], list[str]]],
) -> None:
    puzzle_rows: list[tuple] = []
    theme_rows: list[tuple[str, str]] = []
    for row, themes in batch:
        puzzle_rows.append(tuple(row[c] for c in COLUMNS))
        for theme in themes:
            theme_rows.append((row["puzzle_id"], theme))
    if puzzle_rows:
        conn.executemany(INSERT_SQL, puzzle_rows)
    if theme_rows:
        conn.executemany(INSERT_THEME_SQL, theme_rows)
```

- [ ] **Step 4: Run tests — expect green**

Run: `pytest tests/test_writer.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add ingest/writer.py tests/test_writer.py
git commit -m "feat(ingest): writer module that computes derived cols and bulk-inserts"
```

---

## Task 8: Download module (mockable HTTP)

**Files:**
- Create: `ingest/download.py`
- Create: `tests/test_download.py`

- [ ] **Step 1: Write `tests/test_download.py`**

```python
import time
from pathlib import Path

from ingest.download import ensure_dump, MAX_AGE_SECONDS


class FakeResponse:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def raise_for_status(self) -> None: ...

    def iter_bytes(self, chunk_size: int = 65536):
        for i in range(0, len(self._data), chunk_size):
            yield self._data[i:i + chunk_size]


class FakeStream:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def __enter__(self) -> FakeResponse:
        return FakeResponse(self._data)

    def __exit__(self, *exc) -> None: ...


class FakeClient:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self.called = 0

    def stream(self, method: str, url: str):
        self.called += 1
        return FakeStream(self._data)

    def __enter__(self):
        return self

    def __exit__(self, *exc): ...


def test_ensure_dump_downloads_when_missing(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "dump.zst"
    client = FakeClient(b"hello-world")
    monkeypatch.setattr("ingest.download.httpx.Client", lambda **kw: client)
    ensure_dump(url="http://x", path=target)
    assert target.read_bytes() == b"hello-world"
    assert client.called == 1


def test_ensure_dump_reuses_recent_file(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "dump.zst"
    target.write_bytes(b"old")
    client = FakeClient(b"NEW")
    monkeypatch.setattr("ingest.download.httpx.Client", lambda **kw: client)
    ensure_dump(url="http://x", path=target)
    assert target.read_bytes() == b"old"
    assert client.called == 0


def test_ensure_dump_redownloads_when_stale(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "dump.zst"
    target.write_bytes(b"old")
    old_mtime = time.time() - (MAX_AGE_SECONDS + 1000)
    import os
    os.utime(target, (old_mtime, old_mtime))

    client = FakeClient(b"NEW")
    monkeypatch.setattr("ingest.download.httpx.Client", lambda **kw: client)
    ensure_dump(url="http://x", path=target)
    assert target.read_bytes() == b"NEW"
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/test_download.py -v`
Expected: ImportError.

- [ ] **Step 3: Write `ingest/download.py`**

```python
from __future__ import annotations

import time
from pathlib import Path

import httpx

MAX_AGE_SECONDS = 30 * 24 * 3600  # 30 days


def ensure_dump(url: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        age = time.time() - path.stat().st_mtime
        if age < MAX_AGE_SECONDS:
            return

    with httpx.Client(follow_redirects=True, timeout=None) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with path.open("wb") as fh:
                for chunk in resp.iter_bytes(chunk_size=1 << 16):
                    fh.write(chunk)
```

- [ ] **Step 4: Run tests — expect green**

Run: `pytest tests/test_download.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add ingest/download.py tests/test_download.py
git commit -m "feat(ingest): streaming download with 30-day freshness cache"
```

---

## Task 9: Ingest orchestrator + CLI

**Files:**
- Create: `ingest/run.py`
- Create: `tests/test_run_ingest.py`

- [ ] **Step 1: Write `tests/test_run_ingest.py`**

```python
from pathlib import Path

from app.db import init_db
from ingest.run import ingest_csv_file
import sqlite3


def test_ingest_csv_file_populates_db(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    init_db(db)
    csv_path = Path("tests/fixtures/puzzles_sample.csv")
    inserted = ingest_csv_file(csv_path, db, batch_size=3)
    assert inserted == 10

    conn = sqlite3.connect(db)
    try:
        total = conn.execute("SELECT COUNT(*) FROM puzzles").fetchone()[0]
        mate_in_2 = conn.execute(
            "SELECT COUNT(*) FROM puzzle_themes WHERE theme='mateIn2'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert total == 10
    assert mate_in_2 == 1
```

- [ ] **Step 2: Run tests — expect failure**

Run: `pytest tests/test_run_ingest.py -v`
Expected: ImportError.

- [ ] **Step 3: Write `ingest/run.py`**

```python
from __future__ import annotations

import argparse
import csv
import io
import sqlite3
from pathlib import Path

import zstandard
from tqdm import tqdm

from app.config import settings
from app.db import init_db
from ingest.download import ensure_dump
from ingest.writer import insert_batch, row_from_csv


def _stream_csv(path: Path):
    if path.suffix == ".zst":
        with path.open("rb") as raw:
            dctx = zstandard.ZstdDecompressor()
            with dctx.stream_reader(raw) as decoded:
                text = io.TextIOWrapper(decoded, encoding="utf-8", newline="")
                yield from csv.DictReader(text)
    else:
        with path.open("r", encoding="utf-8", newline="") as fh:
            yield from csv.DictReader(fh)


def ingest_csv_file(csv_path: Path, db_path: Path, batch_size: int = 10_000) -> int:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA journal_mode=MEMORY")
        conn.execute("BEGIN")
        batch: list = []
        total = 0
        for csv_row in tqdm(_stream_csv(csv_path), desc="ingest"):
            batch.append(row_from_csv(csv_row))
            if len(batch) >= batch_size:
                insert_batch(conn, batch)
                total += len(batch)
                batch.clear()
        if batch:
            insert_batch(conn, batch)
            total += len(batch)
        conn.commit()
        conn.execute("VACUUM")
        conn.execute("ANALYZE")
        return total
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest Lichess puzzle dump.")
    parser.add_argument("--csv", type=Path, default=None,
                        help="local CSV (uncompressed) to ingest; skips download")
    args = parser.parse_args()

    if args.csv is not None:
        ingest_csv_file(args.csv, settings.db_path)
        return
    ensure_dump(settings.dump_url, settings.dump_path)
    ingest_csv_file(settings.dump_path, settings.db_path)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests — expect green**

Run: `pytest tests/test_run_ingest.py -v`
Expected: 1 passed.

- [ ] **Step 5: Smoke-test CLI with fixture**

Run:
```bash
rm -f ./data/puzzles.sqlite
python -m ingest.run --csv tests/fixtures/puzzles_sample.csv
sqlite3 ./data/puzzles.sqlite "SELECT COUNT(*) FROM puzzles;"
```
Expected: `10`.

- [ ] **Step 6: Commit**

```bash
git add ingest/run.py tests/test_run_ingest.py
git commit -m "feat(ingest): streaming CSV/zst ingest orchestrator + CLI"
```

---

## Task 10: Filter models (pydantic)

**Files:**
- Create: `app/models.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write `tests/test_models.py`**

```python
import pytest
from pydantic import ValidationError
from app.models import Filters


def test_defaults_all_none():
    f = Filters()
    assert f.rating_min is None
    assert f.themes_any == []
    assert f.themes_all == []


def test_rejects_invalid_side():
    with pytest.raises(ValidationError):
        Filters(side_to_move="x")


def test_rejects_invalid_phase():
    with pytest.raises(ValidationError):
        Filters(phase="midgame")


def test_accepts_lists():
    f = Filters(themes_any=["fork"], themes_all=["mate", "endgame"])
    assert f.themes_any == ["fork"]
    assert f.themes_all == ["mate", "endgame"]
```

- [ ] **Step 2: Run — expect ImportError**

Run: `pytest tests/test_models.py -v`
Expected: ImportError.

- [ ] **Step 3: Write `app/models.py`**

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Filters(BaseModel):
    rating_min: int | None = None
    rating_max: int | None = None
    piece_count_min: int | None = None
    piece_count_max: int | None = None
    move_number_min: int | None = None
    move_number_max: int | None = None
    popularity_min: int | None = None
    nb_plays_min: int | None = None
    themes_any: list[str] = Field(default_factory=list)
    themes_all: list[str] = Field(default_factory=list)
    opening_tags_any: list[str] = Field(default_factory=list)
    side_to_move: Literal["w", "b"] | None = None
    phase: Literal["opening", "middlegame", "endgame"] | None = None
    material_balance_min: int | None = None
    material_balance_max: int | None = None
    has_promoted: bool | None = None
    has_en_passant: bool | None = None
    has_castling: bool | None = None


class Puzzle(BaseModel):
    puzzle_id: str
    fen: str
    moves: str
    rating: int
    rating_deviation: int
    popularity: int
    nb_plays: int
    themes: list[str]
    game_url: str | None
    opening_tags: list[str]
    piece_count: int
    move_number: int
    side_to_move: str
    phase: str
    material_balance: int
    has_promoted: bool
    has_en_passant: bool
    castling_rights: str


class SearchResponse(BaseModel):
    count: int
    sample_ids: list[str]


class RandomResponse(BaseModel):
    count: int
    puzzle: Puzzle | None


class Stats(BaseModel):
    total_puzzles: int
    rating_min: int
    rating_max: int
    piece_count_min: int
    piece_count_max: int
```

- [ ] **Step 4: Run — expect green**

Run: `pytest tests/test_models.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/models.py tests/test_models.py
git commit -m "feat(api): Filters + response pydantic models"
```

---

## Task 11: Filter-to-SQL builder (TDD)

**Files:**
- Create: `app/filters.py`
- Create: `tests/test_filters.py`

- [ ] **Step 1: Write `tests/test_filters.py`**

```python
from app.filters import build_where
from app.models import Filters


def test_empty_filters_has_empty_where():
    sql, params = build_where(Filters())
    assert sql == ""
    assert params == []


def test_range_rating_uses_both_sides():
    sql, params = build_where(Filters(rating_min=1500, rating_max=2000))
    assert "rating >= ?" in sql and "rating <= ?" in sql
    assert params == [1500, 2000]


def test_only_lower_bound():
    sql, params = build_where(Filters(piece_count_min=5))
    assert "piece_count >= ?" in sql
    assert params == [5]


def test_side_and_phase():
    sql, params = build_where(Filters(side_to_move="w", phase="endgame"))
    assert "side_to_move = ?" in sql
    assert "phase = ?" in sql
    assert params == ["w", "endgame"]


def test_themes_any_uses_in_subquery():
    sql, params = build_where(Filters(themes_any=["fork", "pin"]))
    assert "SELECT puzzle_id FROM puzzle_themes WHERE theme IN" in sql
    assert params == ["fork", "pin"]


def test_themes_all_uses_group_having():
    sql, params = build_where(Filters(themes_all=["mate", "endgame"]))
    assert "HAVING COUNT(DISTINCT theme) = ?" in sql
    assert params == ["mate", "endgame", 2]


def test_opening_tag_like():
    sql, params = build_where(Filters(opening_tags_any=["Sicilian_Defense"]))
    assert "opening_tags LIKE ?" in sql
    assert params == ["%Sicilian_Defense%"]


def test_boolean_flags():
    sql, params = build_where(Filters(has_promoted=True, has_en_passant=False))
    assert "has_promoted = ?" in sql
    assert "has_en_passant = ?" in sql
    assert params == [1, 0]


def test_has_castling_true_means_rights_not_dash():
    sql, params = build_where(Filters(has_castling=True))
    assert "castling_rights != '-'" in sql
    assert params == []


def test_has_castling_false_means_no_rights():
    sql, params = build_where(Filters(has_castling=False))
    assert "castling_rights = '-'" in sql
```

- [ ] **Step 2: Run — expect failure**

Run: `pytest tests/test_filters.py -v`
Expected: ImportError.

- [ ] **Step 3: Write `app/filters.py`**

```python
from __future__ import annotations

from app.models import Filters


def _range(col: str, lo, hi) -> tuple[list[str], list]:
    clauses: list[str] = []
    params: list = []
    if lo is not None:
        clauses.append(f"{col} >= ?")
        params.append(lo)
    if hi is not None:
        clauses.append(f"{col} <= ?")
        params.append(hi)
    return clauses, params


def build_where(f: Filters) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []

    for col, lo, hi in [
        ("rating", f.rating_min, f.rating_max),
        ("piece_count", f.piece_count_min, f.piece_count_max),
        ("move_number", f.move_number_min, f.move_number_max),
        ("material_balance", f.material_balance_min, f.material_balance_max),
    ]:
        c, p = _range(col, lo, hi)
        clauses.extend(c); params.extend(p)

    if f.popularity_min is not None:
        clauses.append("popularity >= ?"); params.append(f.popularity_min)
    if f.nb_plays_min is not None:
        clauses.append("nb_plays >= ?"); params.append(f.nb_plays_min)
    if f.side_to_move is not None:
        clauses.append("side_to_move = ?"); params.append(f.side_to_move)
    if f.phase is not None:
        clauses.append("phase = ?"); params.append(f.phase)

    if f.themes_any:
        placeholders = ",".join("?" * len(f.themes_any))
        clauses.append(
            f"puzzle_id IN (SELECT puzzle_id FROM puzzle_themes "
            f"WHERE theme IN ({placeholders}))"
        )
        params.extend(f.themes_any)
    if f.themes_all:
        placeholders = ",".join("?" * len(f.themes_all))
        clauses.append(
            f"puzzle_id IN (SELECT puzzle_id FROM puzzle_themes "
            f"WHERE theme IN ({placeholders}) GROUP BY puzzle_id "
            f"HAVING COUNT(DISTINCT theme) = ?)"
        )
        params.extend(f.themes_all)
        params.append(len(f.themes_all))

    if f.opening_tags_any:
        or_parts = ["opening_tags LIKE ?"] * len(f.opening_tags_any)
        clauses.append("(" + " OR ".join(or_parts) + ")")
        params.extend(f"%{tag}%" for tag in f.opening_tags_any)

    if f.has_promoted is not None:
        clauses.append("has_promoted = ?"); params.append(1 if f.has_promoted else 0)
    if f.has_en_passant is not None:
        clauses.append("has_en_passant = ?"); params.append(1 if f.has_en_passant else 0)
    if f.has_castling is True:
        clauses.append("castling_rights != '-'")
    elif f.has_castling is False:
        clauses.append("castling_rights = '-'")

    sql = " AND ".join(clauses)
    if sql:
        sql = "WHERE " + sql
    return sql, params
```

- [ ] **Step 4: Run — expect green**

Run: `pytest tests/test_filters.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add app/filters.py tests/test_filters.py
git commit -m "feat(api): SQL WHERE builder from Filters pydantic model"
```

---

## Task 12: Query layer (SELECTs using build_where)

**Files:**
- Create: `app/queries.py`
- Create: `tests/test_queries.py`

- [ ] **Step 1: Write `tests/test_queries.py`**

```python
from pathlib import Path

from app.db import init_db, connect
from app.models import Filters
from app.queries import count_puzzles, random_puzzle, list_themes, list_openings, get_stats, get_by_id
from ingest.run import ingest_csv_file


def _populate(tmp_path: Path) -> Path:
    db = tmp_path / "t.sqlite"
    init_db(db)
    ingest_csv_file(Path("tests/fixtures/puzzles_sample.csv"), db)
    return db


def test_count_all(tmp_path: Path) -> None:
    db = _populate(tmp_path)
    with connect(db) as conn:
        assert count_puzzles(conn, Filters()) == 10


def test_count_with_rating_range(tmp_path: Path) -> None:
    db = _populate(tmp_path)
    with connect(db) as conn:
        assert count_puzzles(conn, Filters(rating_min=1500, rating_max=1700)) >= 1


def test_count_themes_all(tmp_path: Path) -> None:
    db = _populate(tmp_path)
    with connect(db) as conn:
        assert count_puzzles(conn, Filters(themes_all=["mate", "mateIn2"])) == 1


def test_random_returns_a_puzzle(tmp_path: Path) -> None:
    db = _populate(tmp_path)
    with connect(db) as conn:
        puzzle = random_puzzle(conn, Filters())
    assert puzzle is not None
    assert puzzle.puzzle_id


def test_random_empty_filter_returns_none(tmp_path: Path) -> None:
    db = _populate(tmp_path)
    with connect(db) as conn:
        p = random_puzzle(conn, Filters(rating_min=9000))
    assert p is None


def test_list_themes_and_openings(tmp_path: Path) -> None:
    db = _populate(tmp_path)
    with connect(db) as conn:
        themes = list_themes(conn)
        openings = list_openings(conn)
    assert "mate" in themes
    assert any("Sicilian" in o for o in openings) or any("Kings_Gambit" in o for o in openings)


def test_stats(tmp_path: Path) -> None:
    db = _populate(tmp_path)
    with connect(db) as conn:
        s = get_stats(conn)
    assert s.total_puzzles == 10
    assert s.rating_min <= s.rating_max


def test_get_by_id(tmp_path: Path) -> None:
    db = _populate(tmp_path)
    with connect(db) as conn:
        p = get_by_id(conn, "00008")
    assert p is not None
    assert p.rating == 1812
```

- [ ] **Step 2: Run — expect ImportError**

Run: `pytest tests/test_queries.py -v`
Expected: ImportError.

- [ ] **Step 3: Write `app/queries.py`**

```python
from __future__ import annotations

import random
import sqlite3

from app.filters import build_where
from app.models import Filters, Puzzle, Stats


def _row_to_puzzle(row: sqlite3.Row) -> Puzzle:
    themes = (row["themes"] or "").split()
    opening_tags = (row["opening_tags"] or "").split() if row["opening_tags"] else []
    return Puzzle(
        puzzle_id=row["puzzle_id"],
        fen=row["fen"],
        moves=row["moves"],
        rating=row["rating"],
        rating_deviation=row["rating_deviation"],
        popularity=row["popularity"],
        nb_plays=row["nb_plays"],
        themes=themes,
        game_url=row["game_url"],
        opening_tags=opening_tags,
        piece_count=row["piece_count"],
        move_number=row["move_number"],
        side_to_move=row["side_to_move"],
        phase=row["phase"],
        material_balance=row["material_balance"],
        has_promoted=bool(row["has_promoted"]),
        has_en_passant=bool(row["has_en_passant"]),
        castling_rights=row["castling_rights"],
    )


def count_puzzles(conn: sqlite3.Connection, filters: Filters) -> int:
    where, params = build_where(filters)
    sql = f"SELECT COUNT(*) AS n FROM puzzles {where}"
    return conn.execute(sql, params).fetchone()["n"]


def sample_ids(conn: sqlite3.Connection, filters: Filters, k: int = 5) -> list[str]:
    where, params = build_where(filters)
    sql = f"SELECT puzzle_id FROM puzzles {where} LIMIT ?"
    rows = conn.execute(sql, [*params, k]).fetchall()
    return [r["puzzle_id"] for r in rows]


def random_puzzle(conn: sqlite3.Connection, filters: Filters) -> Puzzle | None:
    total = count_puzzles(conn, filters)
    if total == 0:
        return None
    offset = random.randrange(total)
    where, params = build_where(filters)
    sql = f"SELECT * FROM puzzles {where} LIMIT 1 OFFSET ?"
    row = conn.execute(sql, [*params, offset]).fetchone()
    return _row_to_puzzle(row) if row else None


def get_by_id(conn: sqlite3.Connection, puzzle_id: str) -> Puzzle | None:
    row = conn.execute(
        "SELECT * FROM puzzles WHERE puzzle_id = ?", (puzzle_id,)
    ).fetchone()
    return _row_to_puzzle(row) if row else None


def list_themes(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT theme FROM puzzle_themes ORDER BY theme"
    ).fetchall()
    return [r["theme"] for r in rows]


def list_openings(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT opening_tags FROM puzzles "
        "WHERE opening_tags IS NOT NULL AND opening_tags <> ''"
    ).fetchall()
    tags: set[str] = set()
    for r in rows:
        for t in r["opening_tags"].split():
            tags.add(t)
    return sorted(tags)


def get_stats(conn: sqlite3.Connection) -> Stats:
    row = conn.execute(
        "SELECT COUNT(*) AS total, "
        "       MIN(rating) AS rmin, MAX(rating) AS rmax, "
        "       MIN(piece_count) AS pmin, MAX(piece_count) AS pmax "
        "FROM puzzles"
    ).fetchone()
    return Stats(
        total_puzzles=row["total"],
        rating_min=row["rmin"] or 0,
        rating_max=row["rmax"] or 0,
        piece_count_min=row["pmin"] or 0,
        piece_count_max=row["pmax"] or 0,
    )
```

- [ ] **Step 4: Run — expect green**

Run: `pytest tests/test_queries.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add app/queries.py tests/test_queries.py
git commit -m "feat(api): query layer (count, random, list themes/openings, stats)"
```

---

## Task 13: FastAPI bootstrap + maintenance mode when DB missing

**Files:**
- Create: `app/main.py`
- Create: `tests/conftest.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write `tests/conftest.py`**

```python
import shutil
from pathlib import Path

import pytest

from app.db import init_db
from ingest.run import ingest_csv_file


@pytest.fixture
def populated_db(tmp_path: Path) -> Path:
    db = tmp_path / "t.sqlite"
    init_db(db)
    ingest_csv_file(Path("tests/fixtures/puzzles_sample.csv"), db)
    return db


@pytest.fixture
def app_with_db(populated_db, monkeypatch):
    from app import config
    monkeypatch.setattr(config.settings, "db_path", populated_db)
    from importlib import reload
    from app import main
    reload(main)
    return main.app


@pytest.fixture
def app_without_db(tmp_path: Path, monkeypatch):
    from app import config
    monkeypatch.setattr(config.settings, "db_path", tmp_path / "missing.sqlite")
    from importlib import reload
    from app import main
    reload(main)
    return main.app
```

- [ ] **Step 2: Write `tests/test_main.py`**

```python
from fastapi.testclient import TestClient


def test_root_serves_index_when_db_exists(app_with_db) -> None:
    (app_with_db := app_with_db)
    c = TestClient(app_with_db)
    r = c.get("/")
    assert r.status_code == 200
    assert "lichess-puzzles" in r.text.lower() or "<!doctype html>" in r.text.lower()


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
    assert "make ingest" in r.text.lower() or "ingest" in r.text.lower()
```

- [ ] **Step 3: Write placeholder `static/index.html` so routing works**

```html
<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8"><title>lichess-puzzles</title></head>
<body><h1>lichess-puzzles</h1><p>Trainer loading...</p></body></html>
```

- [ ] **Step 4: Write `app/main.py`**

```python
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings

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


def _db_exists() -> bool:
    return settings.db_path.exists()


app = FastAPI(title="lichess-puzzles", version="0.1.0")


@app.get("/", response_class=HTMLResponse)
def root() -> HTMLResponse:
    if not _db_exists():
        return HTMLResponse(MAINTENANCE_HTML)
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    return {"ok": True, "db": _db_exists()}


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
```

- [ ] **Step 5: Run tests — expect green**

Run: `pytest tests/test_main.py -v`
Expected: 4 passed.

- [ ] **Step 6: Smoke-test locally**

Run in one shell: `uvicorn app.main:app --port 8000`
Visit `http://localhost:8000/healthz` → JSON. Visit `/` → HTML.

- [ ] **Step 7: Commit**

```bash
git add app/main.py tests/conftest.py tests/test_main.py static/index.html
git commit -m "feat(api): FastAPI bootstrap with maintenance mode fallback"
```

---

## Task 14: Meta router (`/api/stats`, `/api/themes`, `/api/openings`)

**Files:**
- Create: `app/routers/meta.py`
- Modify: `app/main.py` — register router
- Create: `tests/test_meta_router.py`

- [ ] **Step 1: Write `tests/test_meta_router.py`**

```python
from fastapi.testclient import TestClient


def test_stats(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/api/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total_puzzles"] == 10
    assert data["rating_min"] <= data["rating_max"]


def test_themes(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/api/themes")
    assert r.status_code == 200
    assert "mate" in r.json()


def test_openings(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/api/openings")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
```

- [ ] **Step 2: Run — expect 404s (router not yet mounted)**

Run: `pytest tests/test_meta_router.py -v`
Expected: FAIL.

- [ ] **Step 3: Write `app/routers/meta.py`**

```python
from fastapi import APIRouter, Depends

from app.config import settings
from app.db import connect
from app.models import Stats
from app.queries import get_stats, list_themes, list_openings

router = APIRouter(prefix="/api")


def _conn():
    conn = connect(settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


@router.get("/stats", response_model=Stats)
def stats(conn=Depends(_conn)) -> Stats:
    return get_stats(conn)


@router.get("/themes", response_model=list[str])
def themes(conn=Depends(_conn)) -> list[str]:
    return list_themes(conn)


@router.get("/openings", response_model=list[str])
def openings(conn=Depends(_conn)) -> list[str]:
    return list_openings(conn)
```

- [ ] **Step 4: Register in `app/main.py`**

Add near the other imports:
```python
from app.routers import meta as meta_router
```
And after app creation:
```python
app.include_router(meta_router.router)
```

- [ ] **Step 5: Run — expect green**

Run: `pytest tests/test_meta_router.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add app/routers/meta.py app/main.py tests/test_meta_router.py
git commit -m "feat(api): meta router for stats/themes/openings"
```

---

## Task 15: Puzzles router (search, random, by-id)

**Files:**
- Create: `app/routers/puzzles.py`
- Modify: `app/main.py`
- Create: `tests/test_puzzles_router.py`

- [ ] **Step 1: Write `tests/test_puzzles_router.py`**

```python
from fastapi.testclient import TestClient


def test_search_all(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.post("/api/puzzles/search", json={})
    assert r.status_code == 200
    assert r.json()["count"] == 10


def test_search_rating_filter(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.post("/api/puzzles/search", json={"rating_min": 1600, "rating_max": 1800})
    assert r.status_code == 200
    assert 0 < r.json()["count"] <= 10


def test_random_returns_puzzle(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/api/puzzles/random")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 10
    assert body["puzzle"] is not None
    assert "fen" in body["puzzle"]


def test_random_empty_filter(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/api/puzzles/random", params={"rating_min": 9999})
    assert r.status_code == 200
    assert r.json()["puzzle"] is None


def test_get_by_id(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/api/puzzles/00008")
    assert r.status_code == 200
    assert r.json()["rating"] == 1812


def test_get_by_id_404(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/api/puzzles/NOPE")
    assert r.status_code == 404
```

- [ ] **Step 2: Run — FAIL (no router yet)**

Run: `pytest tests/test_puzzles_router.py -v`
Expected: FAIL.

- [ ] **Step 3: Write `app/routers/puzzles.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, Query

from app.config import settings
from app.db import connect
from app.models import Filters, Puzzle, SearchResponse, RandomResponse
from app.queries import count_puzzles, random_puzzle, sample_ids, get_by_id

router = APIRouter(prefix="/api/puzzles")


def _conn():
    conn = connect(settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


def _filters_from_query(
    rating_min: int | None = None, rating_max: int | None = None,
    piece_count_min: int | None = None, piece_count_max: int | None = None,
    move_number_min: int | None = None, move_number_max: int | None = None,
    popularity_min: int | None = None, nb_plays_min: int | None = None,
    themes_any: list[str] = Query(default_factory=list),
    themes_all: list[str] = Query(default_factory=list),
    opening_tags_any: list[str] = Query(default_factory=list),
    side_to_move: str | None = None,
    phase: str | None = None,
    material_balance_min: int | None = None, material_balance_max: int | None = None,
    has_promoted: bool | None = None,
    has_en_passant: bool | None = None,
    has_castling: bool | None = None,
) -> Filters:
    return Filters(
        rating_min=rating_min, rating_max=rating_max,
        piece_count_min=piece_count_min, piece_count_max=piece_count_max,
        move_number_min=move_number_min, move_number_max=move_number_max,
        popularity_min=popularity_min, nb_plays_min=nb_plays_min,
        themes_any=themes_any, themes_all=themes_all,
        opening_tags_any=opening_tags_any,
        side_to_move=side_to_move, phase=phase,
        material_balance_min=material_balance_min,
        material_balance_max=material_balance_max,
        has_promoted=has_promoted,
        has_en_passant=has_en_passant,
        has_castling=has_castling,
    )


@router.post("/search", response_model=SearchResponse)
def search(filters: Filters, conn=Depends(_conn)) -> SearchResponse:
    n = count_puzzles(conn, filters)
    return SearchResponse(count=n, sample_ids=sample_ids(conn, filters, 5))


@router.get("/random", response_model=RandomResponse)
def random_(filters: Filters = Depends(_filters_from_query), conn=Depends(_conn)) -> RandomResponse:
    n = count_puzzles(conn, filters)
    if n == 0:
        return RandomResponse(count=0, puzzle=None)
    return RandomResponse(count=n, puzzle=random_puzzle(conn, filters))


@router.get("/{puzzle_id}", response_model=Puzzle)
def by_id(puzzle_id: str, conn=Depends(_conn)) -> Puzzle:
    p = get_by_id(conn, puzzle_id)
    if p is None:
        raise HTTPException(status_code=404, detail="puzzle not found")
    return p
```

- [ ] **Step 4: Register in `app/main.py`**

Add:
```python
from app.routers import puzzles as puzzles_router
...
app.include_router(puzzles_router.router)
```

- [ ] **Step 5: Run — expect green**

Run: `pytest tests/test_puzzles_router.py -v`
Expected: 6 passed.

- [ ] **Step 6: Full test suite**

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add app/routers/puzzles.py app/main.py tests/test_puzzles_router.py
git commit -m "feat(api): puzzles router (search, random, by-id)"
```

---

## Task 16: Vendor chessground CSS (JS comes via ESM CDN)

**Rationale:** chessground 9.x ships ESM-only. Rather than wire up a bundler,
we'll pull the JS from `esm.sh` as native ES modules at runtime (server-side
deploy still works — only the client needs internet, which it already does to
reach us). We still vendor the CSS locally so the board renders correctly.

**Files:**
- Create: `static/vendor/chessground.base.css`
- Create: `static/vendor/chessground.brown.css`
- Create: `static/vendor/chessground.cburnett.css`

- [ ] **Step 1: Download chessground CSS**

Run:
```bash
mkdir -p static/vendor
curl -L https://unpkg.com/chessground@9.1.1/assets/chessground.base.css \
  -o static/vendor/chessground.base.css
curl -L https://unpkg.com/chessground@9.1.1/assets/chessground.brown.css \
  -o static/vendor/chessground.brown.css
curl -L https://unpkg.com/chessground@9.1.1/assets/chessground.cburnett.css \
  -o static/vendor/chessground.cburnett.css
```
Expected: 3 files downloaded, each > 500 bytes.

- [ ] **Step 2: Verify with a manual smoke page**

Write `static/vendor/smoke.html`:
```html
<!doctype html><meta charset="utf-8"><title>vendor smoke</title>
<link rel="stylesheet" href="chessground.base.css"/>
<link rel="stylesheet" href="chessground.brown.css"/>
<link rel="stylesheet" href="chessground.cburnett.css"/>
<div id="board" style="width:320px;height:320px"></div>
<script type="module">
  import { Chessground } from 'https://esm.sh/chessground@9.1.1';
  import { Chess } from 'https://esm.sh/chess.js@1.0.0';
  const cg = Chessground(document.getElementById('board'), {});
  const g = new Chess();
  document.title = 'vendor ok ' + (cg && g ? 'yes' : 'no');
</script>
```
Run `python -m http.server 8100`, open `http://localhost:8100/static/vendor/smoke.html`. The starting position must render and the title must say `vendor ok yes`.

- [ ] **Step 3: Delete smoke file and commit**

```bash
rm static/vendor/smoke.html
git add static/vendor
git commit -m "chore(frontend): vendor chessground CSS (JS loaded via esm.sh)"
```

---

## Task 17: Frontend API client (`static/js/api.js`)

**Files:**
- Create: `static/js/api.js`

- [ ] **Step 1: Write `static/js/api.js`**

```javascript
export async function fetchStats() {
  const r = await fetch('/api/stats');
  if (!r.ok) throw new Error('stats');
  return r.json();
}

export async function fetchThemes() {
  const r = await fetch('/api/themes');
  return r.ok ? r.json() : [];
}

export async function fetchOpenings() {
  const r = await fetch('/api/openings');
  return r.ok ? r.json() : [];
}

export async function search(filters) {
  const r = await fetch('/api/puzzles/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(filters),
  });
  if (!r.ok) throw new Error('search');
  return r.json();
}

export async function randomPuzzle(filters) {
  const qs = filtersToQueryString(filters);
  const r = await fetch(`/api/puzzles/random${qs ? '?' + qs : ''}`);
  if (!r.ok) throw new Error('random');
  return r.json();
}

function filtersToQueryString(filters) {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(filters)) {
    if (v === null || v === undefined || v === '') continue;
    if (Array.isArray(v)) {
      v.forEach(val => params.append(k, val));
    } else {
      params.append(k, String(v));
    }
  }
  return params.toString();
}
```

- [ ] **Step 2: Commit**

```bash
git add static/js/api.js
git commit -m "feat(frontend): API client (fetchStats/themes/openings/search/random)"
```

---

## Task 18: Frontend `index.html` skeleton + CSS

**Files:**
- Modify: `static/index.html` (replace placeholder)
- Create: `static/css/styles.css`

- [ ] **Step 1: Write `static/css/styles.css`**

```css
:root {
  --bg: #1b1b1b;
  --panel: #242424;
  --panel-2: #2e2e2e;
  --text: #eee;
  --accent: #4a9;
  --border: #3a3a3a;
}
* { box-sizing: border-box; }
html, body {
  margin: 0; padding: 0;
  background: var(--bg); color: var(--text);
  font-family: system-ui, -apple-system, sans-serif;
  height: 100%;
}
header {
  padding: .75rem 1rem;
  background: var(--panel);
  border-bottom: 1px solid var(--border);
  display: flex; gap: 1rem; align-items: center; justify-content: space-between;
}
header h1 { font-size: 1.1rem; margin: 0; }
#counter { color: var(--accent); font-weight: bold; }

main {
  display: grid;
  grid-template-columns: 320px 1fr 320px;
  gap: 1rem; padding: 1rem;
  height: calc(100vh - 52px);
}
@media (max-width: 1000px) {
  main { grid-template-columns: 1fr; height: auto; }
}

.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: .5rem;
  padding: 1rem;
  overflow-y: auto;
}

#board-wrap { display: flex; align-items: center; justify-content: center; }
#board { width: min(60vh, 560px); aspect-ratio: 1/1; }

.preset-row { display: flex; flex-wrap: wrap; gap: .25rem; margin-bottom: 1rem; }
.preset-row button {
  background: var(--panel-2); color: var(--text); border: 1px solid var(--border);
  border-radius: .3rem; padding: .25rem .5rem; cursor: pointer; font-size: .85rem;
}
.preset-row button:hover { background: var(--accent); color: #000; }

details { margin-bottom: .5rem; }
details summary { cursor: pointer; font-weight: bold; padding: .25rem 0; }
.row { display: flex; gap: .5rem; align-items: center; margin: .25rem 0; }
.row label { flex: 1; font-size: .85rem; }
.row input, .row select {
  width: 80px; background: var(--panel-2); color: var(--text);
  border: 1px solid var(--border); border-radius: .2rem; padding: .2rem;
}
.checkbox-list { max-height: 180px; overflow-y: auto; border: 1px solid var(--border); padding: .25rem; }
.checkbox-list label { display: block; font-size: .8rem; }

button.primary {
  background: var(--accent); color: #000; border: 0; border-radius: .3rem;
  padding: .5rem 1rem; cursor: pointer; font-weight: bold; width: 100%;
  margin-top: .5rem;
}
button.secondary {
  background: var(--panel-2); color: var(--text); border: 1px solid var(--border);
  border-radius: .3rem; padding: .4rem .75rem; cursor: pointer; margin: .25rem 0;
  display: block; width: 100%;
}
button:disabled { opacity: .5; cursor: not-allowed; }

.theme-chip {
  display: inline-block; background: var(--panel-2); color: var(--text);
  padding: .1rem .4rem; border-radius: .3rem; font-size: .75rem; margin: .1rem;
}
#status { min-height: 1.5rem; margin: .5rem 0; font-weight: bold; }
.status-ok { color: #4a9; }
.status-err { color: #e55; }
```

- [ ] **Step 2: Replace `static/index.html`**

```html
<!doctype html>
<html lang="pt-br">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>lichess-puzzles</title>
<link rel="stylesheet" href="/static/vendor/chessground.base.css"/>
<link rel="stylesheet" href="/static/vendor/chessground.brown.css"/>
<link rel="stylesheet" href="/static/vendor/chessground.cburnett.css"/>
<link rel="stylesheet" href="/static/css/styles.css"/>
<script type="importmap">
{
  "imports": {
    "chessground": "https://esm.sh/chessground@9.1.1",
    "chess.js":    "https://esm.sh/chess.js@1.0.0"
  }
}
</script>
</head>
<body>
<header>
  <h1>lichess-puzzles</h1>
  <div>Filtrados: <span id="counter">—</span></div>
  <div id="puzzle-meta"></div>
</header>

<main>
  <section class="panel" id="filters">
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
        <input id="popularity_min" type="number" placeholder=""></div>
      <div class="row"><label>NbPlays ≥</label>
        <input id="nb_plays_min" type="number" placeholder=""></div>
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
      <div class="row"><label>Material (brancas − pretas)</label>
        <input id="material_balance_min" type="number" placeholder="min">
        <input id="material_balance_max" type="number" placeholder="max"></div>
      <div class="row"><label>Tem peça promovida</label>
        <select id="has_promoted"><option value="">—</option>
          <option value="true">sim</option><option value="false">não</option></select></div>
      <div class="row"><label>En passant disponível</label>
        <select id="has_en_passant"><option value="">—</option>
          <option value="true">sim</option><option value="false">não</option></select></div>
      <div class="row"><label>Direito de roque</label>
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

    <button class="primary" id="btn-search">Buscar</button>
  </section>

  <section class="panel" id="board-wrap">
    <div id="board"></div>
  </section>

  <section class="panel" id="info">
    <div id="puzzle-info">Escolha filtros e clique Buscar.</div>
    <div id="status"></div>
    <button class="secondary" id="btn-reveal" disabled>Revelar solução</button>
    <button class="secondary" id="btn-reset" disabled>Resetar posição</button>
    <button class="secondary" id="btn-next" disabled>Próximo</button>
    <div id="puzzle-link"></div>
  </section>
</main>

<script type="module" src="/static/js/main.js"></script>
</body>
</html>
```

- [ ] **Step 3: Commit**

```bash
git add static/index.html static/css/styles.css
git commit -m "feat(frontend): 3-column layout HTML and dark CSS"
```

---

## Task 19: Filter UI controller

**Files:**
- Create: `static/js/filters.js`

- [ ] **Step 1: Write `static/js/filters.js`**

```javascript
import { fetchThemes, fetchOpenings, search } from './api.js';

const NUMBER_FIELDS = [
  'rating_min','rating_max','piece_count_min','piece_count_max',
  'move_number_min','move_number_max','popularity_min','nb_plays_min',
  'material_balance_min','material_balance_max',
];
const SELECT_FIELDS = ['side_to_move','phase'];
const BOOL_SELECT_FIELDS = ['has_promoted','has_en_passant','has_castling'];

export async function initFilterUI(onChange) {
  const [themes, openings] = await Promise.all([fetchThemes(), fetchOpenings()]);
  renderCheckboxList('themes_any', themes);
  renderCheckboxList('themes_all', themes);
  renderCheckboxList('opening_tags_any', openings);

  const debounced = debounce(() => onChange(readFilters()), 300);
  for (const id of [...NUMBER_FIELDS, ...SELECT_FIELDS, ...BOOL_SELECT_FIELDS]) {
    document.getElementById(id)?.addEventListener('input', debounced);
  }
  document.querySelectorAll('.checkbox-list input').forEach(cb =>
    cb.addEventListener('change', debounced));
  onChange(readFilters());
}

export function readFilters() {
  const f = {};
  for (const id of NUMBER_FIELDS) {
    const v = document.getElementById(id)?.value;
    if (v !== '' && v !== undefined) f[id] = Number(v);
  }
  for (const id of SELECT_FIELDS) {
    const v = document.getElementById(id)?.value;
    if (v) f[id] = v;
  }
  for (const id of BOOL_SELECT_FIELDS) {
    const v = document.getElementById(id)?.value;
    if (v === 'true') f[id] = true;
    else if (v === 'false') f[id] = false;
  }
  f.themes_any       = collectChecked('themes_any');
  f.themes_all       = collectChecked('themes_all');
  f.opening_tags_any = collectChecked('opening_tags_any');
  return f;
}

export function applyPreset(preset) {
  clearAll();
  for (const [k, v] of Object.entries(preset)) {
    if (Array.isArray(v)) {
      setCheckboxList(k, v);
    } else if (typeof v === 'boolean') {
      const el = document.getElementById(k);
      if (el) el.value = v ? 'true' : 'false';
    } else {
      const el = document.getElementById(k);
      if (el) el.value = v ?? '';
    }
  }
}

export async function updateCounter(filters) {
  try {
    const { count } = await search(filters);
    document.getElementById('counter').textContent = count.toLocaleString('pt-BR');
  } catch {
    document.getElementById('counter').textContent = '—';
  }
}

function clearAll() {
  for (const id of [...NUMBER_FIELDS, ...SELECT_FIELDS, ...BOOL_SELECT_FIELDS]) {
    const el = document.getElementById(id);
    if (el) el.value = '';
  }
  document.querySelectorAll('.checkbox-list input').forEach(cb => cb.checked = false);
}

function renderCheckboxList(containerId, items) {
  const box = document.getElementById(containerId);
  box.innerHTML = '';
  items.forEach(item => {
    const label = document.createElement('label');
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.value = item;
    cb.dataset.group = containerId;
    label.append(cb, ' ', item);
    box.append(label);
  });
}

function collectChecked(containerId) {
  return [...document.querySelectorAll(`#${containerId} input:checked`)].map(cb => cb.value);
}

function setCheckboxList(containerId, values) {
  const set = new Set(values);
  document.querySelectorAll(`#${containerId} input`).forEach(cb => {
    cb.checked = set.has(cb.value);
  });
}

function debounce(fn, ms) {
  let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}
```

- [ ] **Step 2: Commit**

```bash
git add static/js/filters.js
git commit -m "feat(frontend): filter UI controller with debounced counter"
```

---

## Task 20: Trainer (board + move validation)

**Files:**
- Create: `static/js/trainer.js`

- [ ] **Step 1: Write `static/js/trainer.js`**

```javascript
import { Chessground } from 'chessground';
import { Chess } from 'chess.js';
import { randomPuzzle } from './api.js';

const RECENT_MAX = 10;

export function createTrainer() {
  const state = {
    board: null,
    chess: null,
    puzzle: null,
    moveIndex: 0,
    recentIds: [],
    currentFilters: {},
  };

  state.board = Chessground(document.getElementById('board'), {
    movable: { free: false, color: 'white', events: { after: onUserMove } },
    draggable: { showGhost: true },
  });

  async function loadRandom(filters) {
    state.currentFilters = filters;
    for (let attempt = 0; attempt < 4; attempt++) {
      const data = await randomPuzzle(filters);
      if (!data.puzzle) return showNoPuzzle(data.count);
      if (!state.recentIds.includes(data.puzzle.puzzle_id) || data.count <= state.recentIds.length) {
        return loadPuzzle(data.puzzle);
      }
    }
    const data = await randomPuzzle(filters);
    if (data.puzzle) loadPuzzle(data.puzzle);
  }

  function loadPuzzle(puzzle) {
    state.puzzle = puzzle;
    state.moveIndex = 0;
    state.chess = new Chess(puzzle.fen);
    state.recentIds.push(puzzle.puzzle_id);
    if (state.recentIds.length > RECENT_MAX) state.recentIds.shift();
    renderBoardFromChess();
    renderInfo(puzzle);
    setStatus(`Sua vez: ${puzzle.side_to_move === 'w' ? 'brancas' : 'pretas'}`);
    enableButtons(true);
  }

  function renderBoardFromChess() {
    const color = state.puzzle.side_to_move === 'w' ? 'white' : 'black';
    state.board.set({
      fen: state.chess.fen(),
      turnColor: color,
      orientation: color,
      movable: {
        color,
        free: false,
        dests: legalDests(state.chess),
        events: { after: onUserMove },
      },
      lastMove: undefined,
      drawable: { autoShapes: [] },
    });
  }

  function onUserMove(orig, dest) {
    const expectedUci = state.puzzle.moves.split(' ')[state.moveIndex];
    const userUci = orig + dest;
    // handle promotion: chess.js will take promo param; puzzle moves include promo char
    const promo = expectedUci.length === 5 ? expectedUci[4] : undefined;
    const move = state.chess.move({ from: orig, to: dest, promotion: promo });
    if (!move) { // illegal at chess.js level; undo visually
      renderBoardFromChess();
      flash('Jogada ilegal', true);
      return;
    }
    if (move.from + move.to + (move.promotion || '') !== expectedUci) {
      state.chess.undo();
      renderBoardFromChess();
      flash('Tente de novo', true);
      return;
    }
    state.moveIndex += 1;
    flash('Correto!', false);

    const remaining = state.puzzle.moves.split(' ').length - state.moveIndex;
    if (remaining === 0) {
      setStatus('Resolvido ✓ — carregando próximo…', 'ok');
      setTimeout(() => loadRandom(state.currentFilters), 1500);
      return;
    }
    const reply = state.puzzle.moves.split(' ')[state.moveIndex];
    setTimeout(() => {
      state.chess.move({
        from: reply.slice(0,2), to: reply.slice(2,4),
        promotion: reply[4],
      });
      state.moveIndex += 1;
      renderBoardFromChess();
    }, 500);
  }

  function reveal() {
    if (!state.puzzle) return;
    state.chess = new Chess(state.puzzle.fen);
    state.moveIndex = 0;
    renderBoardFromChess();
    const moves = state.puzzle.moves.split(' ');
    const arrows = moves.map((uci, i) => ({
      orig: uci.slice(0,2), dest: uci.slice(2,4),
      brush: i % 2 === 0 ? 'green' : 'blue',
    }));
    state.board.set({ drawable: { autoShapes: arrows } });
    setStatus('Solução revelada', 'ok');
  }

  function reset() {
    if (!state.puzzle) return;
    state.chess = new Chess(state.puzzle.fen);
    state.moveIndex = 0;
    renderBoardFromChess();
    setStatus(`Sua vez: ${state.puzzle.side_to_move === 'w' ? 'brancas' : 'pretas'}`);
  }

  function showNoPuzzle(count) {
    state.puzzle = null;
    document.getElementById('puzzle-info').textContent =
      'Nenhum puzzle com esses filtros — afrouxe algum critério.';
    document.getElementById('puzzle-link').innerHTML = '';
    setStatus(`Total encontrado: ${count}`, 'err');
    enableButtons(false);
  }

  function renderInfo(p) {
    const themes = p.themes.map(t => `<span class="theme-chip">${t}</span>`).join(' ');
    const openings = p.opening_tags.length
      ? `<div>Abertura: ${p.opening_tags.join(', ')}</div>` : '';
    document.getElementById('puzzle-info').innerHTML = `
      <div><strong>ID:</strong> ${p.puzzle_id}</div>
      <div>Rating: ${p.rating} ±${p.rating_deviation}</div>
      <div>Popularidade: ${p.popularity}</div>
      <div>Plays: ${p.nb_plays.toLocaleString('pt-BR')}</div>
      <div>Peças: ${p.piece_count} — Lance: ${p.move_number} — Fase: ${p.phase}</div>
      <div>Material (B−P): ${p.material_balance}</div>
      <div>Themes: ${themes}</div>${openings}`;
    document.getElementById('puzzle-link').innerHTML = p.game_url
      ? `<a href="${p.game_url}" target="_blank" rel="noopener">ver no Lichess ↗</a>` : '';
    document.getElementById('puzzle-meta').textContent =
      `Rating ${p.rating} · Peças ${p.piece_count}`;
  }

  function legalDests(chess) {
    const dests = new Map();
    const squares = [];
    for (const f of 'abcdefgh') for (const r of '12345678') squares.push(f + r);
    for (const sq of squares) {
      const moves = chess.moves({ square: sq, verbose: true });
      if (moves.length) dests.set(sq, moves.map(m => m.to));
    }
    return dests;
  }

  function flash(msg, err) { setStatus(msg, err ? 'err' : 'ok'); }
  function setStatus(text, kind) {
    const el = document.getElementById('status');
    el.textContent = text;
    el.className = kind === 'ok' ? 'status-ok' : kind === 'err' ? 'status-err' : '';
  }
  function enableButtons(v) {
    for (const id of ['btn-reveal','btn-reset','btn-next']) {
      document.getElementById(id).disabled = !v;
    }
  }

  return { loadRandom, reveal, reset };
}
```

- [ ] **Step 2: Commit**

```bash
git add static/js/trainer.js
git commit -m "feat(frontend): trainer with chessground/chess.js validation and rotation"
```

---

## Task 21: Presets + main bootstrap

**Files:**
- Create: `static/presets.json`
- Create: `static/js/main.js`

- [ ] **Step 1: Write `static/presets.json`**

```json
[
  { "name": "Finais básicos", "filters": {
      "piece_count_min": 4, "piece_count_max": 8,
      "phase": "endgame", "rating_min": 1000, "rating_max": 1400 } },
  { "name": "Mate em 1", "filters": { "themes_all": ["mate", "mateIn1"] } },
  { "name": "Mate em 2", "filters": { "themes_all": ["mate", "mateIn2"] } },
  { "name": "Mate em 3", "filters": { "themes_all": ["mate", "mateIn3"] } },
  { "name": "Táticas clássicas", "filters": {
      "phase": "middlegame", "rating_min": 1500, "rating_max": 1900,
      "themes_any": ["fork", "pin", "skewer", "discoveredAttack"] } },
  { "name": "Sacrifícios posicionais", "filters": {
      "themes_all": ["sacrifice"], "rating_min": 1800 } },
  { "name": "Siciliana", "filters": {
      "opening_tags_any": ["Sicilian_Defense"],
      "move_number_min": 10, "move_number_max": 20 } },
  { "name": "Finais de torre", "filters": {
      "phase": "endgame", "themes_any": ["rookEndgame"] } },
  { "name": "Populares", "filters": {
      "popularity_min": 80, "nb_plays_min": 1000 } },
  { "name": "Desafio alto", "filters": {
      "rating_min": 2000, "rating_max": 2400, "popularity_min": 50 } }
]
```

- [ ] **Step 2: Write `static/js/main.js`**

```javascript
import { initFilterUI, readFilters, updateCounter, applyPreset } from './filters.js';
import { createTrainer } from './trainer.js';

async function boot() {
  const trainer = createTrainer();
  await initFilterUI(updateCounter);

  const presets = await fetch('/static/presets.json').then(r => r.json());
  const row = document.getElementById('presets');
  presets.forEach(p => {
    const b = document.createElement('button');
    b.textContent = p.name;
    b.addEventListener('click', async () => {
      applyPreset(p.filters);
      await updateCounter(readFilters());
      await trainer.loadRandom(readFilters());
    });
    row.append(b);
  });

  document.getElementById('btn-search').addEventListener('click', () =>
    trainer.loadRandom(readFilters()));
  document.getElementById('btn-next').addEventListener('click', () =>
    trainer.loadRandom(readFilters()));
  document.getElementById('btn-reveal').addEventListener('click', () => trainer.reveal());
  document.getElementById('btn-reset').addEventListener('click', () => trainer.reset());
}

boot().catch(e => {
  document.getElementById('puzzle-info').textContent = 'Erro ao iniciar: ' + e.message;
});
```

- [ ] **Step 3: Manual smoke test**

Run in the repo root (with `./data/puzzles.sqlite` populated from the fixture):
```bash
uvicorn app.main:app --port 8000
```
Visit `http://localhost:8000`. Verify:
- counter shows "10"
- clicking a preset applies filters and loads a puzzle if any match
- drag-and-drop on the board validates against the solution
- "Próximo" rotates to a new puzzle
- "Revelar solução" shows arrows

Fix any issue you find and re-run until all 5 checks pass. **Do not advance to Task 22 until manual smoke passes.**

- [ ] **Step 4: Commit**

```bash
git add static/presets.json static/js/main.js
git commit -m "feat(frontend): presets and main bootstrap wiring filters+trainer"
```

---

## Task 22: Dockerfile, docker-compose, Makefile

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `Makefile`

- [ ] **Step 1: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
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

- [ ] **Step 2: Write `docker-compose.yml`**

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
      - DUMP_PATH=/app/data/lichess_db_puzzle.csv.zst
    restart: unless-stopped
```

- [ ] **Step 3: Write `Makefile`**

```makefile
.PHONY: build up down logs ingest rebuild test clean

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

ingest:
	docker compose run --rm app python -m ingest.run

rebuild:
	docker compose down
	docker compose build
	docker compose up -d

test:
	docker compose run --rm app pytest -v

clean:
	rm -f data/puzzles.sqlite
```

- [ ] **Step 4: Local Docker smoke**

Run:
```bash
make build
make up
curl -s http://localhost:8004/healthz
make down
```
Expected: `healthz` returns `{"ok":true,"db":false}` (db=false because fresh volume, no ingest yet).

- [ ] **Step 5: Commit**

```bash
git add Dockerfile docker-compose.yml Makefile
git commit -m "build: Dockerfile, compose and Makefile for dev/deploy"
```

---

## Task 23: GitHub Actions deploy workflow

**Files:**
- Create: `.github/workflows/deploy.yml`

- [ ] **Step 1: Write `.github/workflows/deploy.yml`**

```yaml
name: deploy

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: pytest -v

  deploy:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - name: SSH deploy
        uses: appleboy/ssh-action@v1.2.0
        with:
          host: ${{ secrets.SSH_HOST_HOSTINGER02 }}
          username: ${{ secrets.SSH_USER_HOSTINGER02 }}
          key: ${{ secrets.SSH_PRIVATE_KEY_HOSTINGER02 }}
          script: |
            cd /var/local/apps/lichess-puzzles
            GIT_SSH_COMMAND='ssh -i ~/.ssh/lichess_puzzles_deploy_key' git pull
            make rebuild
```

- [ ] **Step 2: Configure the three repo secrets**

In GitHub (`Settings → Secrets and variables → Actions`), add:
- `SSH_HOST_HOSTINGER02` = `72.61.43.231`
- `SSH_USER_HOSTINGER02` = `deployer`
- `SSH_PRIVATE_KEY_HOSTINGER02` = content of a private key that matches a deploy-key on the server

Use `gh secret set` for convenience:
```bash
echo -n "72.61.43.231" | gh secret set SSH_HOST_HOSTINGER02 --repo Atzingen/lichess-puzzles
echo -n "deployer"      | gh secret set SSH_USER_HOSTINGER02 --repo Atzingen/lichess-puzzles
# for the private key, you'll need an existing ed25519 key pair — see Task 24
```

(The `SSH_PRIVATE_KEY_HOSTINGER02` is set after Task 24's deploy-key pair exists.)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: GitHub Actions test + SSH deploy to hostinger-02"
```

---

## Task 24: First-time deploy on hostinger-02

**Files:** none in repo — infra steps.

- [ ] **Step 1: SSH in and prepare directory**

On local machine:
```bash
ssh deployer@72.61.43.231 "mkdir -p /var/local/apps/lichess-puzzles"
```

- [ ] **Step 2: Generate deploy key pair on the server**

```bash
ssh deployer@72.61.43.231 'ssh-keygen -t ed25519 -f ~/.ssh/lichess_puzzles_deploy_key -N ""'
ssh deployer@72.61.43.231 'cat ~/.ssh/lichess_puzzles_deploy_key.pub'
```
Copy the printed public key.

- [ ] **Step 3: Register as repo deploy key (read-only)**

Run locally:
```bash
gh repo deploy-key add - --title "hostinger-02 lichess-puzzles" --repo Atzingen/lichess-puzzles <<'EOF'
<paste the public key from step 2>
EOF
```
Expected: `✓ Deploy key added to Atzingen/lichess-puzzles`.

- [ ] **Step 4: Push the private key into GitHub Actions secret**

From local:
```bash
ssh deployer@72.61.43.231 'cat ~/.ssh/lichess_puzzles_deploy_key' \
  | gh secret set SSH_PRIVATE_KEY_HOSTINGER02 --repo Atzingen/lichess-puzzles
```

- [ ] **Step 5: Clone repo on server using the deploy key**

```bash
ssh deployer@72.61.43.231 <<'EOF'
  cd /var/local/apps/lichess-puzzles
  GIT_SSH_COMMAND='ssh -i ~/.ssh/lichess_puzzles_deploy_key -o StrictHostKeyChecking=accept-new' \
    git clone git@github.com:Atzingen/lichess-puzzles.git .
EOF
```

- [ ] **Step 6: Build and ingest on the server**

```bash
ssh deployer@72.61.43.231 <<'EOF'
  cd /var/local/apps/lichess-puzzles
  make build
  make ingest
EOF
```
Expected: ingest completes (~5-10 min) and prints the total puzzle count > 4 000 000.

- [ ] **Step 7: Start container**

```bash
ssh deployer@72.61.43.231 "cd /var/local/apps/lichess-puzzles && make up"
```

- [ ] **Step 8: Open port 8004 on the server firewall**

Via Hostinger control panel or pfSense (whichever controls the WAN), add an inbound rule for TCP/8004. Then from local:
```bash
curl -s -o /dev/null -w '%{http_code}\n' http://72.61.43.231:8004/healthz
```
Expected: `200`.

- [ ] **Step 9: End-to-end smoke test**

```bash
curl -s http://72.61.43.231:8004/healthz
curl -s http://72.61.43.231:8004/api/stats
curl -s -X POST http://72.61.43.231:8004/api/puzzles/search \
  -H 'content-type: application/json' -d '{"rating_min":1500,"rating_max":1600}'
```
Expected: each returns valid JSON, with `total_puzzles > 4_000_000` in `/api/stats` and a non-zero `count` in `/api/puzzles/search`.

Open `http://72.61.43.231:8004` in a browser. Apply a preset, solve a puzzle, click "Próximo". All must work.

- [ ] **Step 10: Trigger a no-op CI deploy to validate the pipeline**

From local:
```bash
git commit --allow-empty -m "ci: smoke test deploy workflow"
git push
```
Watch the run at `gh run watch --repo Atzingen/lichess-puzzles`. Expected: both jobs pass and the site still responds to `curl /healthz`.

- [ ] **Step 11: Commit a note documenting the server path**

Append to `README.md`:

```markdown
## Deployed at

`hostinger-02` · `deployer@72.61.43.231:/var/local/apps/lichess-puzzles`
Open: <http://72.61.43.231:8004/>
```

Commit:
```bash
git add README.md
git commit -m "docs: deployment URL and server path"
git push
```

---

## Post-plan: manual verification checklist

Before declaring the project complete, manually verify on the deployed URL:

- [ ] `/healthz` → `{"ok": true, "db": true}`
- [ ] `/api/stats` → total > 4M
- [ ] UI loads, counter reflects filter changes in real time (≤ 500 ms)
- [ ] Each of the 10 presets loads a puzzle within filter
- [ ] Drag-and-drop validates moves; wrong moves undo; correct moves advance
- [ ] "Próximo" never repeats within the last 10
- [ ] "Revelar solução" draws arrows for every move in the solution
- [ ] "Resetar posição" restores the original FEN of the current puzzle
- [ ] Filter by `piece_count_min=2, piece_count_max=5` returns only bare-kings-style endgames
- [ ] Filter by `move_number_min=30` returns puzzles from middlegame/endgame onwards
- [ ] CI deploy works end-to-end

If any item fails, open a ticket describing the expected vs observed behavior and address before calling the MVP done.
