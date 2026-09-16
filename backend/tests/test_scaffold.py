from fastapi.testclient import TestClient


def test_health():
    from app.main import app
    with TestClient(app) as c:
        r = c.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
