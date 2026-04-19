import pytest
from pydantic import ValidationError
from app.models import Filters


def test_defaults_all_none():
    f = Filters()
    assert f.rating_min is None
    assert f.themes_any == []
    assert f.themes_all == []


def test_rejects_invalid_side():
    with pytest.raises(ValidationError):
        Filters(side_to_move="x")


def test_rejects_invalid_phase():
    with pytest.raises(ValidationError):
        Filters(phase="midgame")


def test_accepts_lists():
    f = Filters(themes_any=["fork"], themes_all=["mate", "endgame"])
    assert f.themes_any == ["fork"]
    assert f.themes_all == ["mate", "endgame"]
