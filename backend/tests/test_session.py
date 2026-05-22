def _join(client) -> dict:
    klass = client.post("/classes", json={"name": "Econ 101"}).json()
    return client.post(
        "/classes/join",
        json={"join_code": klass["join_code"], "display_name": "Alice"},
    ).json()


def test_me_returns_current_student_with_session_cookie(client):
    session = _join(client)
    response = client.get("/me")

    assert response.status_code == 200
    body = response.json()
    assert body["student_id"] == session["student_id"]
    assert body["display_name"] == "Alice"


def test_me_without_session_returns_401(client):
    # Build a fresh client with no cookies to simulate unauthenticated request.
    from fastapi.testclient import TestClient
    from koherent.main import app

    fresh = TestClient(app)
    response = fresh.get("/me")
    assert response.status_code == 401
