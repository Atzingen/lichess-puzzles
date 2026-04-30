from fastapi.testclient import TestClient


def test_root_serves_config_stub(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/")
    assert r.status_code == 200
    assert "/static/js/config.js" in r.text
    assert "Sessões anteriores" in r.text


def test_explore_serves_old_single_page(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/explore")
    assert r.status_code == 200
    assert "chessground" in r.text.lower()
    assert "/static/js/explore.js" in r.text


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


def test_explore_shows_maintenance_page_when_db_missing(app_without_db) -> None:
    c = TestClient(app_without_db)
    r = c.get("/explore")
    assert r.status_code == 200
    assert "ingest" in r.text.lower()


def test_play_route_serves_html(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/play/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "<!doctype html>" in r.text.lower()


def test_play_route_returns_maintenance_when_no_db(app_without_db) -> None:
    c = TestClient(app_without_db)
    r = c.get("/play/anything")
    assert r.status_code == 200
    assert "ingest" in r.text.lower()
