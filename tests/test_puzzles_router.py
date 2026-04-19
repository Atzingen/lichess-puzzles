from fastapi.testclient import TestClient


def test_search_all(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.post("/api/puzzles/search", json={})
    assert r.status_code == 200
    assert r.json()["count"] == 10


def test_search_rating_filter(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.post("/api/puzzles/search", json={"rating_min": 1600, "rating_max": 1800})
    assert r.status_code == 200
    assert 0 < r.json()["count"] <= 10


def test_random_returns_puzzle(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/api/puzzles/random")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 10
    assert body["puzzle"] is not None
    assert "fen" in body["puzzle"]


def test_random_empty_filter(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/api/puzzles/random", params={"rating_min": 9999})
    assert r.status_code == 200
    assert r.json()["puzzle"] is None


def test_get_by_id(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/api/puzzles/00008")
    assert r.status_code == 200
    assert r.json()["rating"] == 1812


def test_get_by_id_404(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/api/puzzles/NOPE")
    assert r.status_code == 404
