from app.filters import build_where
from app.models import Filters


def test_empty_filters_has_empty_where():
    sql, params = build_where(Filters())
    assert sql == ""
    assert params == []


def test_range_rating_uses_both_sides():
    sql, params = build_where(Filters(rating_min=1500, rating_max=2000))
    assert "rating >= ?" in sql and "rating <= ?" in sql
    assert params == [1500, 2000]


def test_only_lower_bound():
    sql, params = build_where(Filters(piece_count_min=5))
    assert "piece_count >= ?" in sql
    assert params == [5]


def test_side_and_phase():
    sql, params = build_where(Filters(side_to_move="w", phase="endgame"))
    assert "side_to_move = ?" in sql
    assert "phase = ?" in sql
    assert params == ["w", "endgame"]


def test_themes_any_uses_in_subquery():
    sql, params = build_where(Filters(themes_any=["fork", "pin"]))
    assert "SELECT puzzle_id FROM puzzle_themes WHERE theme IN" in sql
    assert params == ["fork", "pin"]


def test_themes_all_uses_group_having():
    sql, params = build_where(Filters(themes_all=["mate", "endgame"]))
    assert "HAVING COUNT(DISTINCT theme) = ?" in sql
    assert params == ["mate", "endgame", 2]


def test_opening_tag_like():
    sql, params = build_where(Filters(opening_tags_any=["Sicilian_Defense"]))
    assert "opening_tags LIKE ?" in sql
    assert params == ["%Sicilian_Defense%"]


def test_boolean_flags():
    sql, params = build_where(Filters(has_promoted=True, has_en_passant=False))
    assert "has_promoted = ?" in sql
    assert "has_en_passant = ?" in sql
    assert params == [1, 0]


def test_has_castling_true_means_rights_not_dash():
    sql, params = build_where(Filters(has_castling=True))
    assert "castling_rights != '-'" in sql
    assert params == []


def test_has_castling_false_means_no_rights():
    sql, params = build_where(Filters(has_castling=False))
    assert "castling_rights = '-'" in sql
