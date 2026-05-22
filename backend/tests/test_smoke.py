from fastapi.testclient import TestClient

from koherent.main import app


def test_app_boots():
    client = TestClient(app)
    # No routes defined yet — 404 just proves the app imports and serves
    response = client.get("/")
    assert response.status_code == 404
