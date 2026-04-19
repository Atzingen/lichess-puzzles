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
