def test_create_class_returns_id_and_join_code(client, db):
    response = client.post("/classes", json={"name": "Econ 101"})

    assert response.status_code == 201
    body = response.json()
    assert "id" in body
    assert body["name"] == "Econ 101"
    assert len(body["join_code"]) == 6
    assert body["join_code"].isalnum()
    assert body["join_code"].isupper()
    assert "owner_token" in body and len(body["owner_token"]) >= 32


def test_create_class_rejects_empty_name(client):
    response = client.post("/classes", json={"name": ""})
    assert response.status_code == 422
