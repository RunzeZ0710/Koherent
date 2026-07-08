import uuid

from koherent.ai.fake import FakeAIClient
from koherent.deps import get_ai_client
from koherent.main import app
from koherent.models import Material, MaterialChunk


def _join(client) -> dict:
    klass = client.post("/classes", json={"name": "Econ 101"}).json()
    client.post(
        "/classes/join",
        json={"join_code": klass["join_code"], "display_name": "Alice"},
    )
    return klass


def _seed_material_chunks(db, class_id: str) -> None:
    fake = FakeAIClient()
    contents = [
        "Elasticity measures the responsiveness of quantity demanded to a change in price.",
        "Markets reach equilibrium where supply equals demand.",
    ]
    vectors = fake.embed(contents)
    material = Material(
        class_id=uuid.UUID(class_id),
        filename="econ_notes.md",
        media_type="text/markdown",
        size_bytes=100,
        extracted_chars=100,
    )
    material.chunks = [
        MaterialChunk(chunk_index=i, content=c, embedding=v)
        for i, (c, v) in enumerate(zip(contents, vectors))
    ]
    db.add(material)
    db.commit()


def test_ask_returns_grounded_answer_with_citations(client, db):
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    try:
        klass = _join(client)
        _seed_material_chunks(db, klass["id"])
        resp = client.post(
            f"/classes/{klass['id']}/ask",
            json={"question": "What does elasticity measure?"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["answer"].startswith("[fake:")
        assert len(body["citations"]) >= 1
        assert any("elasticity" in c["content"].lower() for c in body["citations"])
        assert body["truncated"] is False
    finally:
        app.dependency_overrides.pop(get_ai_client, None)


def test_ask_with_no_indexed_content_returns_400(client):
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    try:
        klass = _join(client)
        resp = client.post(f"/classes/{klass['id']}/ask", json={"question": "anything?"})
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_ai_client, None)


def test_ask_other_class_returns_403(client):
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    try:
        klass = _join(client)
        other = client.post("/classes", json={"name": "Bio 200"}).json()
        client.post(
            "/classes/join",
            json={"join_code": other["join_code"], "display_name": "Mallory"},
        )
        resp = client.post(f"/classes/{klass['id']}/ask", json={"question": "q?"})
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_ai_client, None)


def test_explain_returns_grounded_answer(client, db):
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    try:
        klass = _join(client)
        _seed_material_chunks(db, klass["id"])
        resp = client.post(f"/classes/{klass['id']}/explain", json={"concept": "elasticity"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["answer"].startswith("[fake:")
        assert len(body["citations"]) >= 1
    finally:
        app.dependency_overrides.pop(get_ai_client, None)


class _ExplodingAI(FakeAIClient):
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise RuntimeError("NIM is down")


def test_generation_failure_returns_502(client, db):
    app.dependency_overrides[get_ai_client] = lambda: _ExplodingAI()
    try:
        klass = _join(client)
        _seed_material_chunks(db, klass["id"])
        resp = client.post(f"/classes/{klass['id']}/ask", json={"question": "q?"})
        assert resp.status_code == 502
    finally:
        app.dependency_overrides.pop(get_ai_client, None)
