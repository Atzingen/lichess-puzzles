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
