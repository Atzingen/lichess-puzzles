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
