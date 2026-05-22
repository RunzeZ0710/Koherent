def _create_class(client, name="Econ 101") -> dict:
    response = client.post("/classes", json={"name": name})
    assert response.status_code == 201
    return response.json()


def test_join_existing_class_returns_session_and_sets_cookie(client):
    klass = _create_class(client)
    response = client.post(
        "/classes/join",
        json={"join_code": klass["join_code"], "display_name": "Alice"},
    )

    assert response.status_code == 201
    body = response.json()
    assert "student_id" in body
    assert body["display_name"] == "Alice"
    assert body["class_id"] == klass["id"]
    assert "session_token" in body and len(body["session_token"]) >= 32

    assert "koherent_session" in response.cookies
    assert response.cookies["koherent_session"] == body["session_token"]


def test_join_unknown_code_returns_404(client):
    response = client.post(
        "/classes/join", json={"join_code": "ZZZZZZ", "display_name": "Alice"}
    )
    assert response.status_code == 404


def test_join_duplicate_display_name_returns_409(client):
    klass = _create_class(client)
    payload = {"join_code": klass["join_code"], "display_name": "Alice"}
    assert client.post("/classes/join", json=payload).status_code == 201

    response = client.post("/classes/join", json=payload)
    assert response.status_code == 409
