import sqlite3
from pathlib import Path

from app.db import init_db
from ingest.run import ingest_csv_file


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
