from koherent.ai.fake import FakeAIClient
from koherent.deps import get_ai_client
from koherent.main import app


def _join(client) -> dict:
    klass = client.post("/classes", json={"name": "Econ 101"}).json()
    return client.post(
        "/classes/join",
        json={"join_code": klass["join_code"], "display_name": "Alice"},
    ).json()


def _seed_lecture_with_notes_and_audio(client) -> str:
    _join(client)
    lecture = client.post("/lectures", json={"title": "Supply & Demand"}).json()
    lid = lecture["id"]
    client.post(
        f"/lectures/{lid}/notes",
        json={"content": "marginal revenue equals marginal cost", "client_timestamp_ms": 1000},
    )
    client.post(
        f"/lectures/{lid}/notes",
        json={"content": "the mitochondria is the powerhouse of the cell", "client_timestamp_ms": 2000},
    )
    client.post(
        f"/lectures/{lid}/audio",
        files={"file": ("a.webm", b"\x00\x00\x00", "audio/webm")},
    )
    return lid


def test_process_persists_transcript_chunks_embeddings_and_alignments(client):
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    try:
        lid = _seed_lecture_with_notes_and_audio(client)
        resp = client.post(f"/lectures/{lid}/process")
        assert resp.status_code == 200
        body = resp.json()
        assert body["chunk_count"] >= 1
        assert body["note_count"] == 2
        assert body["alignment_count"] == 2
    finally:
        app.dependency_overrides.pop(get_ai_client, None)


def test_process_is_idempotent(client):
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    try:
        lid = _seed_lecture_with_notes_and_audio(client)
        first = client.post(f"/lectures/{lid}/process").json()
        second = client.post(f"/lectures/{lid}/process").json()
        assert second["note_count"] == first["note_count"] == 2
        assert second["alignment_count"] == 2  # not doubled
    finally:
        app.dependency_overrides.pop(get_ai_client, None)


def test_process_without_audio_returns_400(client):
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    try:
        _join(client)
        lecture = client.post("/lectures", json={"title": "No audio"}).json()
        resp = client.post(f"/lectures/{lecture['id']}/process")
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_ai_client, None)


def _join_other_class(client) -> None:
    other = client.post("/classes", json={"name": "Bio 200"}).json()
    client.post(
        "/classes/join",
        json={"join_code": other["join_code"], "display_name": "Mallory"},
    )


def test_process_rejects_student_from_another_class(client):
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    try:
        lid = _seed_lecture_with_notes_and_audio(client)
        _join_other_class(client)  # switches the session cookie to the other class
        resp = client.post(f"/lectures/{lid}/process")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_ai_client, None)
