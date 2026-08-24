from fastapi.testclient import TestClient

from backend.app.main import FRONTEND_DIST, app


client = TestClient(app)


def test_root():
    response = client.get("/")

    assert response.status_code == 200
    if FRONTEND_DIST.is_dir():
        # frontend/dist has been built locally: "/" serves the SPA, same as
        # it would when deployed as a single Cloud Run service.
        assert "text/html" in response.headers["content-type"]
    else:
        assert response.json() == {
            "name": "Account Growth Intelligence API",
            "version": "0.1.0",
            "status": "running",
        }


def test_health_check():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
