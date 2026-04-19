from fastapi.testclient import TestClient


def test_root_serves_index_when_db_exists(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/")
    assert r.status_code == 200
    assert "lichess-puzzles" in r.text.lower() or "<!doctype html>" in r.text.lower()


def test_health_ok(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "db": True}


def test_health_reports_missing_db(app_without_db) -> None:
    c = TestClient(app_without_db)
    r = c.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "db": False}


def test_root_shows_maintenance_page_when_db_missing(app_without_db) -> None:
    c = TestClient(app_without_db)
    r = c.get("/")
    assert r.status_code == 200
    assert "ingest" in r.text.lower()
