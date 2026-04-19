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
