from fastapi.testclient import TestClient


def test_stats(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/api/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total_puzzles"] == 10
    assert data["rating_min"] <= data["rating_max"]


def test_themes(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/api/themes")
    assert r.status_code == 200
    assert "mate" in r.json()


def test_openings(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/api/openings")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
