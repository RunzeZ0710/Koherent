from koherent.ai.fake import FakeAIClient
from koherent.deps import get_ai_client
from koherent.main import app


def _seed_processed_lecture_with_code(client) -> tuple[str, str]:
    """Class + student + lecture with notes and audio, processed with the fake AI.

    Returns (lecture_id, join_code) so tests can join the same class as a
    second student.
    """
    klass = client.post("/classes", json={"name": "Econ 101"}).json()
    client.post(
        "/classes/join",
        json={"join_code": klass["join_code"], "display_name": "Alice"},
    )
    lecture = client.post("/lectures", json={"title": "Supply & Demand"}).json()
    lid = lecture["id"]
    client.post(
        f"/lectures/{lid}/notes",
        json={"content": "marginal revenue equals marginal cost", "client_timestamp_ms": 1000},
    )
    client.post(
        f"/lectures/{lid}/notes",
        json={
            "content": "the mitochondria is the powerhouse of the cell",
            "client_timestamp_ms": 2000,
        },
    )
    client.post(f"/lectures/{lid}/audio", files={"file": ("a.webm", b"\x00", "audio/webm")})
    client.post(f"/lectures/{lid}/process")
    return lid, klass["join_code"]


def _seed_processed_lecture(client) -> str:
    lid, _ = _seed_processed_lecture_with_code(client)
    return lid


def test_post_summary_generates_and_get_returns_cached(client):
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    try:
        lid = _seed_processed_lecture(client)
        post = client.post(f"/lectures/{lid}/summary")
        assert post.status_code == 200
        assert post.json()["content"].startswith("[fake:")
        get = client.get(f"/lectures/{lid}/summary")
        assert get.status_code == 200
        assert get.json()["content"] == post.json()["content"]
    finally:
        app.dependency_overrides.pop(get_ai_client, None)


def test_post_summary_twice_overwrites_single_row(client):
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    try:
        lid = _seed_processed_lecture(client)
        first = client.post(f"/lectures/{lid}/summary")
        second = client.post(f"/lectures/{lid}/summary")
        assert second.status_code == 200
        assert second.json()["content"] == first.json()["content"]  # deterministic fake
    finally:
        app.dependency_overrides.pop(get_ai_client, None)


def test_summary_of_unprocessed_lecture_returns_400(client):
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    try:
        klass = client.post("/classes", json={"name": "Econ 101"}).json()
        client.post(
            "/classes/join",
            json={"join_code": klass["join_code"], "display_name": "Alice"},
        )
        lecture = client.post("/lectures", json={"title": "L"}).json()
        assert client.post(f"/lectures/{lecture['id']}/summary").status_code == 400
        assert client.get(f"/lectures/{lecture['id']}/summary").status_code == 404
    finally:
        app.dependency_overrides.pop(get_ai_client, None)


def test_review_targets_weak_notes(client):
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    try:
        lid = _seed_processed_lecture(client)
        resp = client.post(f"/lectures/{lid}/review")
        assert resp.status_code == 200
        body = resp.json()
        assert body["content"].startswith("[fake:")
        assert body["weak_note_count"] >= 1  # the mitochondria note is off-topic
        assert body["weak_note_count"] <= 3
    finally:
        app.dependency_overrides.pop(get_ai_client, None)


def test_review_without_notes_returns_400(client):
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    try:
        lid, join_code = _seed_processed_lecture_with_code(client)
        # Bob joins the same class but has no notes in this lecture
        client.post("/classes/join", json={"join_code": join_code, "display_name": "Bob"})
        assert client.post(f"/lectures/{lid}/review").status_code == 400
    finally:
        app.dependency_overrides.pop(get_ai_client, None)
