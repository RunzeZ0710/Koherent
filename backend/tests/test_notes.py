def _start_lecture(client) -> dict:
    klass = client.post("/classes", json={"name": "Econ 101"}).json()
    client.post(
        "/classes/join",
        json={"join_code": klass["join_code"], "display_name": "Alice"},
    )
    return client.post("/lectures", json={"title": "Day 1"}).json()


def test_post_note_persists_and_returns_id(client):
    lecture = _start_lecture(client)
    response = client.post(
        f"/lectures/{lecture['id']}/notes",
        json={"content": "MR = MC at the profit-maximizing output", "client_timestamp_ms": 12345},
    )
    assert response.status_code == 201
    body = response.json()
    assert "id" in body
    assert body["content"] == "MR = MC at the profit-maximizing output"
    assert body["client_timestamp_ms"] == 12345


def test_post_note_to_other_class_lecture_returns_403(client):
    # Create lecture in class A as Alice
    lecture_a = _start_lecture(client)

    # Switch identity: join a NEW class as Bob, then try to post to lecture A
    klass_b = client.post("/classes", json={"name": "Hist 101"}).json()
    client.post(
        "/classes/join",
        json={"join_code": klass_b["join_code"], "display_name": "Bob"},
    )
    # Bob's cookie is now active. Posting to lecture_a should be forbidden.
    response = client.post(
        f"/lectures/{lecture_a['id']}/notes",
        json={"content": "trespass", "client_timestamp_ms": 1},
    )
    assert response.status_code == 403


def test_post_note_to_unknown_lecture_returns_404(client):
    klass = client.post("/classes", json={"name": "Econ 101"}).json()
    client.post(
        "/classes/join",
        json={"join_code": klass["join_code"], "display_name": "Alice"},
    )
    response = client.post(
        "/lectures/00000000-0000-0000-0000-000000000000/notes",
        json={"content": "x", "client_timestamp_ms": 1},
    )
    assert response.status_code == 404
