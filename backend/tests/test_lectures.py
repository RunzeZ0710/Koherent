def _join(client) -> dict:
    klass = client.post("/classes", json={"name": "Econ 101"}).json()
    session = client.post(
        "/classes/join",
        json={"join_code": klass["join_code"], "display_name": "Alice"},
    ).json()
    return {**session, "join_code": klass["join_code"]}


def test_start_lecture_returns_id_and_started_at(client):
    _join(client)
    response = client.post("/lectures", json={"title": "Day 1: supply curves"})

    assert response.status_code == 201
    body = response.json()
    assert "id" in body
    assert body["title"] == "Day 1: supply curves"
    assert "started_at" in body
    assert body["ended_at"] is None


def test_start_lecture_without_session_returns_401(client):
    # Use a fresh TestClient with no cookies to simulate unauthenticated request
    from fastapi.testclient import TestClient
    from koherent.main import app
    fresh = TestClient(app)
    response = fresh.post("/lectures", json={"title": "x"})
    assert response.status_code == 401


def test_get_lecture_returns_status(client):
    klass = client.post("/classes", json={"name": "Econ 101"}).json()
    client.post(
        "/classes/join",
        json={"join_code": klass["join_code"], "display_name": "Alice"},
    )
    lecture = client.post("/lectures", json={"title": "Day 1"}).json()

    response = client.get(f"/lectures/{lecture['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == lecture["id"]
    assert body["title"] == "Day 1"
    assert body["ended_at"] is None
    assert body["my_notes_count"] == 0
    assert body["has_audio"] is False
