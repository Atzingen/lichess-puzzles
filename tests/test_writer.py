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
