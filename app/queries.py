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
