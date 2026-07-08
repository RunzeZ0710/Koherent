from koherent.pipeline.report import is_anomaly


def test_below_threshold_is_anomaly():
    assert is_anomaly(0.1, threshold=0.2) is True


def test_at_or_above_threshold_is_not_anomaly():
    assert is_anomaly(0.2, threshold=0.2) is False
    assert is_anomaly(0.9, threshold=0.2) is False


def test_missing_similarity_is_anomaly():
    assert is_anomaly(None, threshold=0.2) is True


from koherent.ai.fake import FakeAIClient  # noqa: E402
from koherent.deps import get_ai_client  # noqa: E402
from koherent.main import app  # noqa: E402


def _join(client) -> dict:
    klass = client.post("/classes", json={"name": "Econ 101"}).json()
    return client.post(
        "/classes/join",
        json={"join_code": klass["join_code"], "display_name": "Alice"},
    ).json()


def _seed_processed_lecture(client) -> str:
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
    client.post(f"/lectures/{lid}/audio", files={"file": ("a.webm", b"\x00\x00\x00", "audio/webm")})
    client.post(f"/lectures/{lid}/process")
    return lid


def test_report_shape_and_anomaly_flag_follows_threshold(client):
    # The fake embedder is bag-of-words and NOT semantically meaningful (real
    # semantic quality is shown by the committed sample). So the HTTP test asserts
    # the route's actual contract: shape, every note linked, and the anomaly flag
    # derived correctly from similarity vs the configured threshold.
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    try:
        lid = _seed_processed_lecture(client)
        report = client.get(f"/lectures/{lid}/report").json()

        assert report["lecture_id"] == lid
        assert "threshold" in report
        assert len(report["items"]) == 2
        threshold = report["threshold"]
        for item in report["items"]:
            assert item["matched_content"] is not None  # both notes linked to the one chunk
            assert isinstance(item["similarity"], float)
            assert item["anomaly"] == (item["similarity"] < threshold)
    finally:
        app.dependency_overrides.pop(get_ai_client, None)


def test_report_flags_everything_when_threshold_is_high(client, monkeypatch):
    # Drive the anomaly=True branch end-to-end through HTTP, deterministically:
    # with an impossibly high threshold every note is "not clearly covered".
    from koherent.config import settings

    monkeypatch.setattr(settings, "anomaly_threshold", 1.5)
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    try:
        lid = _seed_processed_lecture(client)
        report = client.get(f"/lectures/{lid}/report").json()
        assert report["threshold"] == 1.5
        assert all(item["anomaly"] is True for item in report["items"])
    finally:
        app.dependency_overrides.pop(get_ai_client, None)


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


def test_report_rejects_student_from_another_class(client):
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    try:
        lid = _seed_lecture_with_notes_and_audio(client)
        client.post(f"/lectures/{lid}/process")
        other = client.post("/classes", json={"name": "Bio 200"}).json()
        client.post(
            "/classes/join",
            json={"join_code": other["join_code"], "display_name": "Mallory"},
        )
        assert client.get(f"/lectures/{lid}/report").status_code == 403
    finally:
        app.dependency_overrides.pop(get_ai_client, None)


def test_report_only_returns_callers_notes(client):
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    try:
        klass = client.post("/classes", json={"name": "Econ 101"}).json()
        client.post(
            "/classes/join",
            json={"join_code": klass["join_code"], "display_name": "Alice"},
        )
        lecture = client.post("/lectures", json={"title": "L1"}).json()
        lid = lecture["id"]
        client.post(
            f"/lectures/{lid}/notes",
            json={"content": "alice note", "client_timestamp_ms": 1000},
        )
        client.post(f"/lectures/{lid}/audio", files={"file": ("a.webm", b"\x00", "audio/webm")})
        # Bob joins the same class and adds his own note
        client.post(
            "/classes/join",
            json={"join_code": klass["join_code"], "display_name": "Bob"},
        )
        client.post(
            f"/lectures/{lid}/notes",
            json={"content": "bob note", "client_timestamp_ms": 2000},
        )
        client.post(f"/lectures/{lid}/process")
        report = client.get(f"/lectures/{lid}/report").json()
        contents = [item["note_content"] for item in report["items"]]
        assert contents == ["bob note"]  # Bob's session sees only Bob's notes
    finally:
        app.dependency_overrides.pop(get_ai_client, None)
