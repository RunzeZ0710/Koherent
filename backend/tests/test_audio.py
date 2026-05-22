import io


def _start_lecture(client) -> dict:
    klass = client.post("/classes", json={"name": "Econ 101"}).json()
    client.post(
        "/classes/join",
        json={"join_code": klass["join_code"], "display_name": "Alice"},
    )
    return client.post("/lectures", json={"title": "Day 1"}).json()


def test_upload_audio_persists_file_and_row(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIO_STORAGE_DIR", str(tmp_path))
    # The settings instance is already loaded — patch directly:
    from koherent.config import settings

    monkeypatch.setattr(settings, "audio_storage_dir", str(tmp_path))

    lecture = _start_lecture(client)
    fake_audio = b"OggS\x00\x02fake-webm-bytes" * 100  # ~1.7 KB of bytes

    response = client.post(
        f"/lectures/{lecture['id']}/audio",
        files={"file": ("lecture.webm", io.BytesIO(fake_audio), "audio/webm")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["lecture_id"] == lecture["id"]
    assert body["mime_type"] == "audio/webm"
    assert body["size_bytes"] == len(fake_audio)

    saved = tmp_path / body["file_path"].split("/")[-1]
    assert saved.exists()
    assert saved.read_bytes() == fake_audio


def test_upload_audio_rejects_non_audio_mime(client):
    lecture = _start_lecture(client)
    response = client.post(
        f"/lectures/{lecture['id']}/audio",
        files={"file": ("evil.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert response.status_code == 415
