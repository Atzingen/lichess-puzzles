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
