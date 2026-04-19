from pathlib import Path

import pytest

from app.db import init_db
from ingest.run import ingest_csv_file


@pytest.fixture
def populated_db(tmp_path: Path) -> Path:
    db = tmp_path / "t.sqlite"
    init_db(db)
    ingest_csv_file(Path("tests/fixtures/puzzles_sample.csv"), db)
    return db


@pytest.fixture
def app_with_db(populated_db, monkeypatch):
    from app import config
    monkeypatch.setattr(config.settings, "db_path", populated_db)
    from importlib import reload
    from app import main
    reload(main)
    return main.app


@pytest.fixture
def app_without_db(tmp_path: Path, monkeypatch):
    from app import config
    monkeypatch.setattr(config.settings, "db_path", tmp_path / "missing.sqlite")
    from importlib import reload
    from app import main
    reload(main)
    return main.app
