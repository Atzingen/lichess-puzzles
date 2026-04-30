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


def test_batch_returns_at_most_limit_and_filters_rating(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/api/puzzles/batch?rating_min=1500&rating_max=2000&limit=3")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == len(body["puzzles"]) <= 3
    for p in body["puzzles"]:
        assert 1500 <= p["rating"] <= 2000


def test_batch_default_limit_caps_at_available(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/api/puzzles/batch")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == len(body["puzzles"])
    assert body["count"] <= 500


def test_batch_rejects_zero_limit(app_with_db) -> None:
    c = TestClient(app_with_db)
    r = c.get("/api/puzzles/batch?limit=0")
    assert r.status_code == 422
