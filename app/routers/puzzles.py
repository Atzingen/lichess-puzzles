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
