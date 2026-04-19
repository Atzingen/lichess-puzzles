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
