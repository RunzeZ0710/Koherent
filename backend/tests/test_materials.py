from koherent.ai.fake import FakeAIClient
from koherent.deps import get_ai_client
from koherent.main import app
from koherent.models import MaterialChunk


def _join(client) -> dict:
    klass = client.post("/classes", json={"name": "Econ 101"}).json()
    client.post(
        "/classes/join",
        json={"join_code": klass["join_code"], "display_name": "Alice"},
    )
    return klass


def _upload(client, class_id: str, filename: str = "econ_notes.md"):
    content = b"# Elasticity\n\nElasticity measures responsiveness of quantity to price."
    return client.post(
        f"/classes/{class_id}/materials",
        files={"file": (filename, content, "text/markdown")},
    )


def test_upload_material_persists_chunks_with_embeddings(client, db):
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    try:
        klass = _join(client)
        resp = _upload(client, klass["id"])
        assert resp.status_code == 201
        body = resp.json()
        assert body["filename"] == "econ_notes.md"
        assert body["chunk_count"] >= 1
        chunks = db.query(MaterialChunk).all()
        assert len(chunks) == body["chunk_count"]
        assert all(len(c.embedding) > 0 for c in chunks)
    finally:
        app.dependency_overrides.pop(get_ai_client, None)


def test_upload_unsupported_type_returns_415(client):
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    try:
        klass = _join(client)
        resp = client.post(
            f"/classes/{klass['id']}/materials",
            files={"file": ("slides.docx", b"...", "application/octet-stream")},
        )
        assert resp.status_code == 415
    finally:
        app.dependency_overrides.pop(get_ai_client, None)


def test_upload_empty_document_returns_422(client):
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    try:
        klass = _join(client)
        resp = client.post(
            f"/classes/{klass['id']}/materials",
            files={"file": ("empty.txt", b"   ", "text/plain")},
        )
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.pop(get_ai_client, None)


def test_upload_to_another_class_returns_403(client):
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    try:
        klass = _join(client)  # Alice's class
        other = client.post("/classes", json={"name": "Bio 200"}).json()
        client.post(
            "/classes/join",
            json={"join_code": other["join_code"], "display_name": "Mallory"},
        )
        assert _upload(client, klass["id"]).status_code == 403
    finally:
        app.dependency_overrides.pop(get_ai_client, None)


def test_list_materials(client):
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    try:
        klass = _join(client)
        _upload(client, klass["id"])
        resp = client.get(f"/classes/{klass['id']}/materials")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["chunk_count"] >= 1
    finally:
        app.dependency_overrides.pop(get_ai_client, None)
