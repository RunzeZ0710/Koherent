# Koherent Portfolio MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the note→transcript retrieval slice so the repo is a complete, runnable, well-narrated data-integration project worth linking on an internship application.

**Architecture:** A FastAPI pipeline hidden behind one `AIClient` seam transcribes lecture audio, slices it into ~30s chunks, embeds chunks + student notes, links each note to its best-matching chunk by cosine similarity, and flags notes that match nothing as anomalies. The whole pipeline runs offline against a deterministic `FakeAIClient`; a real NVIDIA adapter (Riva ASR + NIM embeddings) implements the same seam for one committed real-data sample.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0 + Postgres, Alembic, pytest, numpy (present), NVIDIA Riva client (present), OpenAI SDK (added in Task 3 for the NIM embeddings endpoint).

## Global Constraints

- **Python** `>=3.11`; **ruff** line-length `100`, target `py311`.
- **Branch:** work on `week-2a-retrieval-pipeline` (already checked out). One commit per task.
- **Test command:** `cd backend && uv run pytest` — requires the Postgres test DB. From repo root run `docker compose up -d` first (Postgres on port `5433`, DB `koherent_test`).
- **TDD:** every behavior change starts with a failing test. Frequent commits.
- **The seam is sacred:** all NVIDIA/network specifics live inside `ai/` adapters. `pipeline/` and `routes/` depend only on the `AIClient` Protocol (`transcribe`, `embed`).
- **No new runtime dependency** except `openai>=1.0` (Task 3).
- **Commit trailer:** end every commit message with
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

### Task 1: Implement cosine similarity + alignment

The 10 tests in `tests/test_alignment.py` already exist and fail (`NotImplementedError`). This task only fills in the two stubbed functions. Pure Python, no DB, no numpy.

**Files:**
- Modify: `backend/src/koherent/pipeline/alignment.py`
- Test: `backend/tests/test_alignment.py` (exists — do not edit)

**Interfaces:**
- Produces: `cosine(a: list[float], b: list[float]) -> float`; `align(note_vectors: list[list[float]], chunk_vectors: list[list[float]]) -> list[AlignmentResult]` where `AlignmentResult(note_index: int, chunk_index: int, similarity: float)` is already defined in the module.

- [ ] **Step 1: Run the existing tests to confirm they fail**

Run: `cd backend && uv run pytest tests/test_alignment.py -q`
Expected: 10 FAILED, all `NotImplementedError`.

- [ ] **Step 2: Implement `cosine` and `align`**

Replace the two `raise NotImplementedError(...)` bodies in `backend/src/koherent/pipeline/alignment.py` (keep the existing imports/docstrings; add `import math` at the top):

```python
import math


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def align(
    note_vectors: list[list[float]],
    chunk_vectors: list[list[float]],
) -> list[AlignmentResult]:
    results: list[AlignmentResult] = []
    for note_index, note_vec in enumerate(note_vectors):
        best_index = -1
        best_similarity = 0.0
        for chunk_index, chunk_vec in enumerate(chunk_vectors):
            similarity = cosine(note_vec, chunk_vec)
            # strict `>` so the EARLIEST chunk wins on a tie
            if best_index == -1 or similarity > best_similarity:
                best_index = chunk_index
                best_similarity = similarity
        if best_index == -1:
            continue  # no chunks to match against
        results.append(
            AlignmentResult(
                note_index=note_index,
                chunk_index=best_index,
                similarity=best_similarity,
            )
        )
    return results
```

- [ ] **Step 3: Run the tests to verify they pass**

Run: `cd backend && uv run pytest tests/test_alignment.py -q`
Expected: 10 passed.

- [ ] **Step 4: Commit**

```bash
cd backend && uv run ruff check src/koherent/pipeline/alignment.py
git add src/koherent/pipeline/alignment.py
git commit -m "$(printf 'feat(pipeline): implement cosine similarity and note-chunk alignment\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 2: Make the `AIClient` seam return `Transcription`

Today `AIClient.transcribe` is typed `-> str`, but `chunking.py` needs per-word timestamps and `riva.py` already returns the richer `Transcription`. Resolve the mismatch toward `Transcription` so the pipeline runs identically on fake and real data.

**Files:**
- Modify: `backend/src/koherent/ai/base.py` (Protocol return type)
- Modify: `backend/src/koherent/ai/fake.py` (synthesize word timings)
- Test: `backend/tests/test_fake_ai.py` (update the two transcribe tests; add one)

**Interfaces:**
- Consumes: `Transcription(text: str, words: list[TranscriptWord])` and `TranscriptWord(word: str, start_ms: int, end_ms: int)` from `koherent.ai.base`.
- Produces: `FakeAIClient.transcribe(audio_path: str) -> Transcription`; `AIClient.transcribe` Protocol now returns `Transcription`. `FakeAIClient.embed` is unchanged.

- [ ] **Step 1: Update the failing tests first**

Replace the two transcribe tests at the bottom of `backend/tests/test_fake_ai.py` and add a chunking-compatibility test:

```python
def test_transcribe_returns_transcription_with_words():
    from koherent.ai.base import Transcription

    ai = FakeAIClient()
    result = ai.transcribe("anything.webm")
    assert isinstance(result, Transcription)
    assert len(result.text) > 0
    assert len(result.words) > 0
    assert result.words[0].word == result.text.split()[0]


def test_transcribe_words_have_increasing_timestamps():
    ai = FakeAIClient()
    words = ai.transcribe("anything.webm").words
    starts = [w.start_ms for w in words]
    assert starts == sorted(starts)
    assert all(w.end_ms >= w.start_ms for w in words)


def test_transcribe_can_be_overridden():
    ai = FakeAIClient(transcript="custom lecture text")
    result = ai.transcribe("ignored.webm")
    assert result.text == "custom lecture text"
    assert [w.word for w in result.words] == ["custom", "lecture", "text"]
```

Run: `cd backend && uv run pytest tests/test_fake_ai.py -q`
Expected: the three transcribe tests FAIL (FakeAIClient still returns `str`); the two `embed` tests still pass.

- [ ] **Step 2: Update the Protocol return type**

In `backend/src/koherent/ai/base.py`, change the `transcribe` signature in the `AIClient` Protocol:

```python
    def transcribe(self, audio_path: str) -> Transcription:
        """Return the transcript (text + per-word timestamps) for the audio file."""
        ...
```

(`Transcription` is already defined above in this file.)

- [ ] **Step 3: Synthesize word timings in `FakeAIClient`**

In `backend/src/koherent/ai/fake.py`, add the import and rewrite `transcribe`:

```python
from koherent.ai.base import Transcription, TranscriptWord

# ...inside FakeAIClient...

    _WORD_MS = 400  # synthetic cadence: one word every 400ms

    def transcribe(self, audio_path: str) -> Transcription:
        words: list[TranscriptWord] = []
        for i, token in enumerate(self._transcript.split()):
            start = i * self._WORD_MS
            words.append(TranscriptWord(word=token, start_ms=start, end_ms=start + 300))
        return Transcription(text=self._transcript, words=words)
```

- [ ] **Step 4: Run the fake-AI tests**

Run: `cd backend && uv run pytest tests/test_fake_ai.py -q`
Expected: all passed.

- [ ] **Step 5: Run the full suite (nothing else should break)**

Run: `cd backend && uv run pytest -q`
Expected: all passed (Task 1 + Task 2 green; everything else still green).

- [ ] **Step 6: Commit**

```bash
cd backend && uv run ruff check src/koherent/ai/base.py src/koherent/ai/fake.py
git add src/koherent/ai/base.py src/koherent/ai/fake.py tests/test_fake_ai.py
git commit -m "$(printf 'refactor(ai): transcribe() returns Transcription so the pipeline runs offline\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 3: Real NIM embeddings adapter

Replace the empty placeholder `ai/embeddings.py` with an adapter that calls NVIDIA NIM's `nvidia/nv-embedqa-e5-v5` over the OpenAI-compatible endpoint. All NVIDIA specifics stay inside this module; the response→vectors mapping is pure and unit-tested with a fake response (no network in tests).

**Files:**
- Modify: `backend/pyproject.toml` (add `openai>=1.0`)
- Rewrite: `backend/src/koherent/ai/embeddings.py`
- Test: `backend/tests/test_embeddings.py` (new)

**Interfaces:**
- Produces: `NIMEmbedder(api_key: str | None = None, model: str = "nvidia/nv-embedqa-e5-v5", input_type: str = "passage")` with `.embed(texts: list[str]) -> list[list[float]]`; module-level pure helper `_response_to_vectors(response) -> list[list[float]]`.

- [ ] **Step 1: Add the dependency**

Edit `backend/pyproject.toml`, adding to the `dependencies` list:

```toml
    "openai>=1.0",
```

Run: `cd backend && uv sync`
Expected: resolves and installs `openai`.

- [ ] **Step 2: Write the failing mapping test**

Create `backend/tests/test_embeddings.py`:

```python
from koherent.ai.embeddings import _response_to_vectors


class _Item:
    def __init__(self, embedding):
        self.embedding = embedding


class _Response:
    def __init__(self, data):
        self.data = data


def test_response_to_vectors_preserves_order_and_shape():
    response = _Response([_Item([0.1, 0.2]), _Item([0.3, 0.4])])
    assert _response_to_vectors(response) == [[0.1, 0.2], [0.3, 0.4]]


def test_response_to_vectors_empty():
    assert _response_to_vectors(_Response([])) == []
```

Run: `cd backend && uv run pytest tests/test_embeddings.py -q`
Expected: FAIL — `ImportError` / `_response_to_vectors` undefined.

- [ ] **Step 3: Implement the adapter**

Replace the entire contents of `backend/src/koherent/ai/embeddings.py`:

```python
"""Real embeddings via NVIDIA NIM (`nvidia/nv-embedqa-e5-v5`), behind the AIClient seam.

This adapter turns texts into vectors. NIM exposes an OpenAI-compatible
embeddings endpoint, so we use the OpenAI SDK pointed at NVIDIA's base URL.
The query/passage asymmetry of embedqa models is handled with `input_type`;
we embed everything as "passage" for the MVP (documented refinement: embed
notes as "query"). All NVIDIA specifics are contained here.
"""

from openai import OpenAI

from koherent.config import settings

_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
_EMBED_MODEL = "nvidia/nv-embedqa-e5-v5"


def _response_to_vectors(response) -> list[list[float]]:
    """Pure mapping from an OpenAI-style embeddings response to plain vectors.

    Order is preserved (item i corresponds to input text i). Untyped on
    purpose — this is the boundary we accept from the SDK and immediately
    convert, so nothing downstream depends on the SDK's shape.
    """
    return [list(item.embedding) for item in response.data]


class NIMEmbedder:
    """Embeddings adapter: list[str] -> list[vector] via hosted NIM."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = _EMBED_MODEL,
        input_type: str = "passage",
    ) -> None:
        key = api_key or settings.nvidia_api_key
        if not key:
            raise ValueError("NVIDIA API key is required (set NVIDIA_API_KEY).")
        self._client = OpenAI(base_url=_NIM_BASE_URL, api_key=key)
        self._model = model
        self._input_type = input_type

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(
            model=self._model,
            input=texts,
            extra_body={"input_type": self._input_type, "truncate": "END"},
        )
        return _response_to_vectors(response)
```

- [ ] **Step 4: Run the test**

Run: `cd backend && uv run pytest tests/test_embeddings.py -q`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
cd backend && uv run ruff check src/koherent/ai/embeddings.py tests/test_embeddings.py
git add pyproject.toml uv.lock src/koherent/ai/embeddings.py tests/test_embeddings.py
git commit -m "$(printf 'feat(ai): add NIM embeddings adapter behind the seam\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 4: Orchestrator + process endpoint

Wire the four stages into one idempotent function and expose `POST /lectures/{id}/process`. Add the real composite client and its DI provider so tests can override it with the fake.

**Files:**
- Create: `backend/src/koherent/ai/real.py` (composite: Riva + NIM behind the seam)
- Create: `backend/src/koherent/pipeline/process.py` (orchestrator)
- Create: `backend/src/koherent/routes/processing.py` (the route)
- Modify: `backend/src/koherent/deps.py` (add `get_ai_client`)
- Modify: `backend/src/koherent/schemas.py` (add `ProcessResult`)
- Modify: `backend/src/koherent/main.py` (register the router)
- Test: `backend/tests/test_processing.py` (new)

**Interfaces:**
- Consumes: `align` (Task 1), `chunk_transcript` (exists), `FakeAIClient` (Task 2), `Transcript`/`TranscriptChunk`/`Note`/`NoteAlignment`/`AudioRecording`/`Lecture` (models).
- Produces: `process_lecture(lecture_id: uuid.UUID, db: Session, ai: AIClient) -> ProcessSummary` where `ProcessSummary(transcript_id: uuid.UUID, chunk_count: int, note_count: int, alignment_count: int)`; `get_ai_client() -> AIClient`; route `POST /lectures/{lecture_id}/process -> ProcessResult`.

- [ ] **Step 1: Write the failing integration test**

Create `backend/tests/test_processing.py`:

```python
from fastapi.testclient import TestClient

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
```

Run: `cd backend && uv run pytest tests/test_processing.py -q`
Expected: FAIL — `cannot import name 'get_ai_client'` / route 404.

- [ ] **Step 2: Add the composite real client**

Create `backend/src/koherent/ai/real.py`:

```python
"""The real AIClient: NVIDIA Riva ASR for transcription + NIM for embeddings.

Composes two adapters behind the single seam. Constructed only for real runs
(both adapters require an NVIDIA API key); tests override the DI provider with
FakeAIClient, so this is never built during the offline suite.
"""

from koherent.ai.base import Transcription
from koherent.ai.embeddings import NIMEmbedder
from koherent.ai.riva import RivaClient


class RealAIClient:
    def __init__(self, transcriber=None, embedder=None) -> None:
        self._transcriber = transcriber or RivaClient()
        self._embedder = embedder or NIMEmbedder()

    def transcribe(self, audio_path: str) -> Transcription:
        return self._transcriber.transcribe(audio_path)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._embedder.embed(texts)
```

- [ ] **Step 3: Add the DI provider**

Append to `backend/src/koherent/deps.py`:

```python
from koherent.ai.base import AIClient
from koherent.ai.real import RealAIClient


def get_ai_client() -> AIClient:
    """Real NVIDIA-backed client for production; tests override with FakeAIClient."""
    return RealAIClient()
```

- [ ] **Step 4: Add the `ProcessResult` schema**

Append to `backend/src/koherent/schemas.py`:

```python
class ProcessResult(BaseModel):
    transcript_id: uuid.UUID
    chunk_count: int
    note_count: int
    alignment_count: int
```

- [ ] **Step 5: Write the orchestrator**

Create `backend/src/koherent/pipeline/process.py`:

```python
"""Orchestrator: run the four pipeline stages for one lecture and persist results.

Idempotent: a re-run clears this lecture's derived rows (transcript -> cascades
chunks; alignments) and rebuilds them, so processing twice yields the same state.
Holds no clever logic of its own — chunking and alignment live in their own
modules; transcription and embedding live behind the AIClient seam.
"""

import os
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from koherent.ai.base import AIClient
from koherent.config import settings
from koherent.models import (
    AudioRecording,
    Lecture,
    Note,
    NoteAlignment,
    Transcript,
    TranscriptChunk,
)
from koherent.pipeline.alignment import align
from koherent.pipeline.chunking import chunk_transcript


@dataclass(frozen=True)
class ProcessSummary:
    transcript_id: uuid.UUID
    chunk_count: int
    note_count: int
    alignment_count: int


class NoAudioError(Exception):
    """Raised when a lecture has no audio recording to process."""


def process_lecture(lecture_id: uuid.UUID, db: Session, ai: AIClient) -> ProcessSummary:
    lecture = db.get(Lecture, lecture_id)
    if lecture is None:
        raise LookupError("lecture not found")

    recording = db.scalar(
        select(AudioRecording)
        .where(AudioRecording.lecture_id == lecture_id)
        .order_by(AudioRecording.created_at)
    )
    if recording is None:
        raise NoAudioError()

    notes = list(db.scalars(select(Note).where(Note.lecture_id == lecture_id)))

    # --- idempotency: clear derived rows in FK-safe order ---
    note_ids = [n.id for n in notes]
    if note_ids:
        db.execute(delete(NoteAlignment).where(NoteAlignment.note_id.in_(note_ids)))
    existing = db.scalar(select(Transcript).where(Transcript.lecture_id == lecture_id))
    if existing is not None:
        db.delete(existing)  # cascades to its chunks
    for note in notes:
        note.embedding = None
    db.flush()

    # --- stage 1: transcribe ---
    audio_path = os.path.join(settings.audio_storage_dir, recording.file_path)
    transcription = ai.transcribe(audio_path)
    transcript = Transcript(lecture_id=lecture_id, full_text=transcription.text)
    db.add(transcript)
    db.flush()

    # --- stage 2: chunk ---
    chunks = chunk_transcript(transcription.words)

    # --- stage 3: embed chunks + notes ---
    chunk_vectors = ai.embed([c.content for c in chunks]) if chunks else []
    chunk_rows: list[TranscriptChunk] = []
    for chunk, vector in zip(chunks, chunk_vectors):
        row = TranscriptChunk(
            transcript_id=transcript.id,
            chunk_index=chunk.index,
            content=chunk.content,
            start_ms=chunk.start_ms,
            end_ms=chunk.end_ms,
            embedding=vector,
        )
        db.add(row)
        chunk_rows.append(row)
    db.flush()

    note_vectors = ai.embed([n.content for n in notes]) if notes else []
    for note, vector in zip(notes, note_vectors):
        note.embedding = vector
    db.flush()

    # --- stage 4: align ---
    alignments = align(note_vectors, [row.embedding for row in chunk_rows])
    for result in alignments:
        db.add(
            NoteAlignment(
                note_id=notes[result.note_index].id,
                transcript_chunk_id=chunk_rows[result.chunk_index].id,
                similarity=result.similarity,
            )
        )

    db.commit()
    return ProcessSummary(
        transcript_id=transcript.id,
        chunk_count=len(chunk_rows),
        note_count=len(notes),
        alignment_count=len(alignments),
    )
```

- [ ] **Step 6: Write the route**

Create `backend/src/koherent/routes/processing.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from koherent.ai.base import AIClient
from koherent.deps import get_ai_client, get_current_student, get_db
from koherent.models import Student
from koherent.pipeline.process import NoAudioError, process_lecture
from koherent.schemas import ProcessResult

router = APIRouter(prefix="/lectures", tags=["processing"])


@router.post("/{lecture_id}/process", response_model=ProcessResult)
def process(
    lecture_id: uuid.UUID,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
    ai: AIClient = Depends(get_ai_client),
) -> ProcessResult:
    try:
        summary = process_lecture(lecture_id, db, ai)
    except LookupError:
        raise HTTPException(status_code=404, detail="Lecture not found")
    except NoAudioError:
        raise HTTPException(status_code=400, detail="Lecture has no audio to process")
    return ProcessResult(
        transcript_id=summary.transcript_id,
        chunk_count=summary.chunk_count,
        note_count=summary.note_count,
        alignment_count=summary.alignment_count,
    )
```

- [ ] **Step 7: Register the router**

In `backend/src/koherent/main.py`, update the import and registration:

```python
from koherent.routes import classes, lectures, processing
```

```python
app.include_router(classes.router)
app.include_router(lectures.router)
app.include_router(processing.router)
```

- [ ] **Step 8: Run the processing tests**

Run: `cd backend && uv run pytest tests/test_processing.py -q`
Expected: 3 passed.

- [ ] **Step 9: Run the full suite**

Run: `cd backend && uv run pytest -q`
Expected: all passed.

- [ ] **Step 10: Commit**

```bash
cd backend && uv run ruff check src/koherent/ tests/test_processing.py
git add src/koherent/ai/real.py src/koherent/pipeline/process.py src/koherent/routes/processing.py src/koherent/deps.py src/koherent/schemas.py src/koherent/main.py tests/test_processing.py
git commit -m "$(printf 'feat(pipeline): orchestrate processing and expose POST /lectures/{id}/process\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 5: Report endpoint with anomaly flagging

Expose `GET /lectures/{id}/report`: every note, the lecture span it linked to, the similarity, and an `anomaly` flag for notes that matched nothing well. The threshold decision is a pure, unit-tested helper; the HTTP test asserts shape + the robust relative property (a transcript-echoing note scores higher than an off-topic one).

**Files:**
- Create: `backend/src/koherent/pipeline/report.py` (pure `is_anomaly`)
- Modify: `backend/src/koherent/config.py` (add `anomaly_threshold`)
- Modify: `backend/src/koherent/schemas.py` (add report schemas)
- Modify: `backend/src/koherent/routes/processing.py` (add the GET route)
- Test: `backend/tests/test_report.py` (new)

**Interfaces:**
- Consumes: `process_lecture` (Task 4), `FakeAIClient`, models with their relationships (`Note.alignment`, `NoteAlignment.chunk`).
- Produces: `is_anomaly(similarity: float | None, threshold: float) -> bool`; schemas `NoteReportItem`, `LectureReport`; route `GET /lectures/{lecture_id}/report -> LectureReport`.

- [ ] **Step 1: Write the failing unit test for `is_anomaly`**

Create `backend/tests/test_report.py`:

```python
from koherent.pipeline.report import is_anomaly


def test_below_threshold_is_anomaly():
    assert is_anomaly(0.1, threshold=0.2) is True


def test_at_or_above_threshold_is_not_anomaly():
    assert is_anomaly(0.2, threshold=0.2) is False
    assert is_anomaly(0.9, threshold=0.2) is False


def test_missing_similarity_is_anomaly():
    assert is_anomaly(None, threshold=0.2) is True
```

Run: `cd backend && uv run pytest tests/test_report.py -q`
Expected: FAIL — module `koherent.pipeline.report` does not exist.

- [ ] **Step 2: Implement `is_anomaly`**

Create `backend/src/koherent/pipeline/report.py`:

```python
"""Pure report helpers, kept free of DB/HTTP so the threshold logic is unit-tested.

A note is an *anomaly* when it does not clearly correspond to anything the
lecture actually said: either it never aligned (no match) or its best match is
below the similarity threshold. This is the seed of cross-student misconception
detection (deferred): a note that matches nothing the professor said is exactly
what we want to surface.
"""


def is_anomaly(similarity: float | None, threshold: float) -> bool:
    return similarity is None or similarity < threshold
```

Run: `cd backend && uv run pytest tests/test_report.py -q`
Expected: 3 passed.

- [ ] **Step 3: Add the threshold to config**

In `backend/src/koherent/config.py`, add a field to `Settings` (after `nvidia_api_key`):

```python
    anomaly_threshold: float = 0.2
```

- [ ] **Step 4: Add the report schemas**

Append to `backend/src/koherent/schemas.py`:

```python
class NoteReportItem(BaseModel):
    note_id: uuid.UUID
    student_id: uuid.UUID
    note_content: str
    client_timestamp_ms: int
    matched_chunk_index: int | None
    matched_content: str | None
    matched_start_ms: int | None
    matched_end_ms: int | None
    similarity: float | None
    anomaly: bool


class LectureReport(BaseModel):
    lecture_id: uuid.UUID
    threshold: float
    items: list[NoteReportItem]
```

- [ ] **Step 5: Add the failing HTTP test**

Append to `backend/tests/test_report.py`:

```python
from fastapi.testclient import TestClient  # noqa: E402

from koherent.ai.fake import FakeAIClient  # noqa: E402
from koherent.deps import get_ai_client  # noqa: E402
from koherent.main import app  # noqa: E402


def _join(client) -> dict:
    klass = client.post("/classes", json={"name": "Econ 101"}).json()
    return client.post(
        "/classes/join",
        json={"join_code": klass["join_code"], "display_name": "Alice"},
    ).json()


def test_report_lists_notes_with_anomaly_flags(client):
    app.dependency_overrides[get_ai_client] = lambda: FakeAIClient()
    try:
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

        report = client.get(f"/lectures/{lid}/report").json()
        assert report["lecture_id"] == lid
        assert len(report["items"]) == 2
        by_content = {i["note_content"]: i for i in report["items"]}
        on_topic = by_content["marginal revenue equals marginal cost"]
        off_topic = by_content["the mitochondria is the powerhouse of the cell"]
        # robust relative property guaranteed by the fake embedder's design
        assert on_topic["similarity"] > off_topic["similarity"]
        assert on_topic["matched_content"] is not None
    finally:
        app.dependency_overrides.pop(get_ai_client, None)
```

Run: `cd backend && uv run pytest tests/test_report.py::test_report_lists_notes_with_anomaly_flags -q`
Expected: FAIL — `GET /lectures/{id}/report` returns 404 / 405.

- [ ] **Step 6: Implement the GET route**

In `backend/src/koherent/routes/processing.py`, add imports and the route. Update the import lines:

```python
from sqlalchemy import select

from koherent.config import settings
from koherent.models import Lecture, Note, Student
from koherent.pipeline.report import is_anomaly
from koherent.schemas import LectureReport, NoteReportItem, ProcessResult
```

Add at the end of the file:

```python
@router.get("/{lecture_id}/report", response_model=LectureReport)
def report(
    lecture_id: uuid.UUID,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
) -> LectureReport:
    if db.get(Lecture, lecture_id) is None:
        raise HTTPException(status_code=404, detail="Lecture not found")

    notes = list(db.scalars(select(Note).where(Note.lecture_id == lecture_id)))
    items: list[NoteReportItem] = []
    for note in notes:
        alignment = note.alignment
        chunk = alignment.chunk if alignment is not None else None
        similarity = alignment.similarity if alignment is not None else None
        items.append(
            NoteReportItem(
                note_id=note.id,
                student_id=note.student_id,
                note_content=note.content,
                client_timestamp_ms=note.client_timestamp_ms,
                matched_chunk_index=chunk.chunk_index if chunk is not None else None,
                matched_content=chunk.content if chunk is not None else None,
                matched_start_ms=chunk.start_ms if chunk is not None else None,
                matched_end_ms=chunk.end_ms if chunk is not None else None,
                similarity=similarity,
                anomaly=is_anomaly(similarity, settings.anomaly_threshold),
            )
        )
    return LectureReport(
        lecture_id=lecture_id, threshold=settings.anomaly_threshold, items=items
    )
```

- [ ] **Step 7: Run the report tests, then the full suite**

Run: `cd backend && uv run pytest tests/test_report.py -q`
Expected: 4 passed.
Run: `cd backend && uv run pytest -q`
Expected: all passed.

- [ ] **Step 8: Commit**

```bash
cd backend && uv run ruff check src/koherent/ tests/test_report.py
git add src/koherent/pipeline/report.py src/koherent/config.py src/koherent/schemas.py src/koherent/routes/processing.py tests/test_report.py
git commit -m "$(printf 'feat(pipeline): add GET /lectures/{id}/report with anomaly flagging\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 6: Committed real-data sample report

Produce the artifact a reader sees without running anything: the pipeline run once on the real cached lecture transcript with a handful of realistic notes (one deliberately wrong), rendered to `samples/`. Uses the real embedder when a key is present; otherwise falls back to the fake embedder with an honest disclosure header. This task runs a script and inspects its output (not TDD — there is no behavior to assert beyond "it wrote a believable artifact").

**Files:**
- Create: `backend/tests/fixtures/sample_transcript.json` (the real cached transcription, moved from the scratch file)
- Create: `backend/scripts/run_sample_report.py`
- Create: `samples/sample_report.json`, `samples/sample_report.md` (generated)

- [ ] **Step 1: Move the real cached transcript into a fixture**

```bash
cd /Users/runzezhang/Documents/GitHub/Koherent
cp backend/scratch_test2.json backend/tests/fixtures/sample_transcript.json
```

Confirm it has `text` and `words` keys:
Run: `cd backend && uv run python -c "import json; d=json.load(open('tests/fixtures/sample_transcript.json')); print(len(d['text']), len(d['words']))"`
Expected: two positive integers.

- [ ] **Step 2: Write the sample script**

Create `backend/scripts/run_sample_report.py`:

```python
"""Generate the committed sample report from the real cached lecture transcript.

Runs the actual pipeline pieces (chunking, embedding, alignment, anomaly flag)
on a fixed set of realistic student notes — one of them deliberately wrong — and
writes samples/sample_report.{json,md}. Uses the real NIM embedder when
NVIDIA_API_KEY is set; otherwise falls back to the deterministic FakeAIClient and
says so in the artifact header. Never fabricates real output.
"""

import json
import os

from koherent.ai.base import TranscriptWord
from koherent.config import settings
from koherent.pipeline.alignment import align
from koherent.pipeline.chunking import chunk_transcript
from koherent.pipeline.report import is_anomaly

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FIXTURE = os.path.join(HERE, "..", "tests", "fixtures", "sample_transcript.json")
OUT_DIR = os.path.join(ROOT, "samples")

NOTES = [
    "the market clears at the price where supply meets demand",
    "a firm maximizes profit where marginal revenue equals marginal cost",
    "a price floor below equilibrium creates a shortage",  # deliberately wrong
    "photosynthesis converts sunlight into chemical energy",  # off-topic anomaly
]


def _load_words() -> list[TranscriptWord]:
    with open(FIXTURE) as fh:
        data = json.load(fh)
    return [TranscriptWord(**w) for w in data["words"]]


def _embedder():
    if settings.nvidia_api_key:
        from koherent.ai.embeddings import NIMEmbedder

        return NIMEmbedder(), "real:nvidia/nv-embedqa-e5-v5"
    from koherent.ai.fake import FakeAIClient

    return FakeAIClient(), "fake:deterministic-bag-of-words (no NVIDIA_API_KEY set)"


def main() -> None:
    words = _load_words()
    chunks = chunk_transcript(words)
    embedder, source = _embedder()

    chunk_vectors = embedder.embed([c.content for c in chunks])
    note_vectors = embedder.embed(NOTES)
    alignments = align(note_vectors, chunk_vectors)

    by_note = {a.note_index: a for a in alignments}
    items = []
    for i, note in enumerate(NOTES):
        a = by_note.get(i)
        chunk = chunks[a.chunk_index] if a is not None else None
        similarity = a.similarity if a is not None else None
        items.append(
            {
                "note": note,
                "matched_span_ms": [chunk.start_ms, chunk.end_ms] if chunk else None,
                "matched_lecture_text": chunk.content if chunk else None,
                "similarity": round(similarity, 4) if similarity is not None else None,
                "anomaly": is_anomaly(similarity, settings.anomaly_threshold),
            }
        )

    report = {
        "embedding_source": source,
        "anomaly_threshold": settings.anomaly_threshold,
        "items": items,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "sample_report.json"), "w") as fh:
        json.dump(report, fh, indent=2)

    lines = [
        "# Sample report",
        "",
        f"_Embedding source: `{source}`. Anomaly threshold: {settings.anomaly_threshold}._",
        "",
        "| Student note | Linked lecture span | Similarity | Anomaly |",
        "| --- | --- | ---: | :---: |",
    ]
    for it in items:
        span = it["matched_lecture_text"] or "—"
        sim = it["similarity"] if it["similarity"] is not None else "—"
        flag = "⚠️ yes" if it["anomaly"] else "no"
        lines.append(f"| {it['note']} | {span} | {sim} | {flag} |")
    with open(os.path.join(OUT_DIR, "sample_report.md"), "w") as fh:
        fh.write("\n".join(lines) + "\n")

    print(f"wrote {OUT_DIR}/sample_report.json and .md (source: {source})")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run the script and inspect the output**

Run: `cd backend && uv run python scripts/run_sample_report.py`
Expected: prints the "wrote ..." line. Then:
Run: `cat ../samples/sample_report.md`
Expected: a 4-row table; the "photosynthesis" row is flagged `⚠️ yes`; on-topic econ notes link to real transcript spans. (If the embedding source is `fake:...`, that is fine and honestly labeled — the README will note a real run can regenerate it.)

- [ ] **Step 4: Commit**

```bash
cd /Users/runzezhang/Documents/GitHub/Koherent
git add backend/tests/fixtures/sample_transcript.json backend/scripts/run_sample_report.py samples/sample_report.json samples/sample_report.md
git commit -m "$(printf 'docs(sample): committed real-data report artifact + generator script\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 7: Repo hygiene — remove scratch/spike files

A portfolio repo root must read as intentional. Remove the throwaway spike/scratch files now that the real cached transcript lives in a fixture.

**Files:**
- Delete: `backend/scratch_investigate.py`, `backend/scratch_pipeline.py`, `backend/spike_asr.py`, `backend/scratch_test2.json`, `backend/scratch_transcription1.json`
- Modify: `backend/.gitignore` or root `.gitignore` (ignore a future `backend/scratch/`)

- [ ] **Step 1: Delete the files**

```bash
cd /Users/runzezhang/Documents/GitHub/Koherent/backend
rm -f scratch_investigate.py scratch_pipeline.py spike_asr.py scratch_test2.json scratch_transcription1.json
```

- [ ] **Step 2: Ignore future scratch work**

Append to the root `.gitignore`:

```gitignore
# local scratch / spikes (never committed)
backend/scratch/
backend/scratch_*.py
backend/scratch_*.json
backend/spike_*.py
```

- [ ] **Step 3: Verify the suite still passes (fixtures, not scratch, are now the source)**

Run: `cd backend && uv run pytest -q`
Expected: all passed.

- [ ] **Step 4: Commit**

```bash
cd /Users/runzezhang/Documents/GitHub/Koherent
git add -A
git commit -m "$(printf 'chore: remove scratch/spike files; ignore future scratch\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

### Task 8: README rewrite + decision log

The narrative is half the value. Reframe the repo around data integration / record linkage, show the architecture, make it runnable in 60 seconds offline, link the sample, and be honest about what is built vs designed-next.

**Files:**
- Rewrite: `README.md` (root)
- Modify: `docs/wiki/DECISIONS.md` (append the new decisions)

- [ ] **Step 1: Rewrite `README.md`**

Replace the root `README.md` with content covering exactly these sections (write real prose; keep it tight):

1. **One-liner + what it is:** Koherent links messy, free-typed student notes to the authoritative lecture transcript they refer to, scores each link, and flags notes that match nothing the professor actually said.
2. **The data-integration framing:** raw inputs (audio + free text) → entities (transcript chunks, notes) → linked, scored relationships (note→chunk alignment) → derived signal (anomaly flags). Position the anomaly flag as the seed of cross-student misconception detection.
3. **Architecture diagram** — include this fenced block verbatim:

```
audio ──Riva ASR──▶ transcript ──chunk(30s)──▶ chunks ──┐
                                                         ├─embed─▶ vectors ─cosine─▶ note→chunk links + score ─▶ anomaly flag
student notes ───────────────────────────────────────────┘
        (all AI behind one AIClient seam: FakeAIClient offline · NVIDIA Riva+NIM real)
```

4. **Run it in 60 seconds (offline, no API key):**

```bash
docker compose up -d                 # Postgres on :5433
cd backend && uv sync
uv run alembic upgrade head
uv run pytest                         # whole pipeline, green, no network
uv run python scripts/run_sample_report.py   # regenerate samples/sample_report.md
```

5. **Sample output:** link `samples/sample_report.md` and describe the off-topic note being flagged.
6. **The seam / V1→V2:** one paragraph — the pipeline depends only on `AIClient`; `FakeAIClient` runs it offline and deterministically, `RealAIClient` swaps in NVIDIA Riva (ASR) + NIM (`nv-embedqa-e5-v5`) with no pipeline change.
7. **Built vs. Designed-Next:** Built = capture (notes + audio), transcription, chunking, embedding, note→chunk linking + scoring, per-note anomaly flagging, the report. Designed-next (link the specs) = cross-student misconception **clustering** ("off the rails") dashboard and the LLM claim-extraction / LLM-as-judge feedback layer. Be explicit that clustering is not yet built.

- [ ] **Step 2: Verify the 60-second steps actually run**

Run each command from Step 1's section 4 in order. Expected: `pytest` green; the sample script writes the artifact. Fix the README if any command is wrong.

- [ ] **Step 3: Append decisions to the wiki**

Append to `docs/wiki/DECISIONS.md` (follow the existing `D-0xx` format and numbering already in that file — read it first to continue the sequence). Record:
- `AIClient.transcribe` returns `Transcription` (text + word timings), not `str`, so chunking runs uniformly on fake and real backends.
- Embeddings via NIM `nvidia/nv-embedqa-e5-v5` over the OpenAI-compatible endpoint, behind a dedicated adapter; everything embedded as `passage` for the MVP (query/passage asymmetry noted as a refinement).
- Anomaly = best similarity below a hand-tuned threshold (`anomaly_threshold`, default `0.2`); a tunable starting point, the seed of misconception detection.
- The committed `samples/sample_report.*` is generated from the real cached transcript; falls back to the fake embedder with a disclosed header when no key is present.

- [ ] **Step 4: Commit**

```bash
cd /Users/runzezhang/Documents/GitHub/Koherent
git add README.md docs/wiki/DECISIONS.md
git commit -m "$(printf 'docs: reframe README around data integration; log Week 2A decisions\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Self-Review (completed)

**Spec coverage:** seam fix → Task 2; finish centerpiece (cosine/align + real embedder) → Tasks 1, 3; orchestrator + process endpoint + DI → Task 4; report + anomaly flag + threshold → Task 5; committed real-data sample → Task 6; repo hygiene → Task 7; README + wiki → Task 8. Every done-bar item in the spec maps to a task.

**Placeholder scan:** no "TBD"/"handle edge cases"-style gaps; the one literal placeholder line in Task 4 Step 6 is explicitly flagged with removal instructions. All code steps show complete code.

**Type consistency:** `Transcription`/`TranscriptWord` (Task 2) consumed by chunking + orchestrator (Task 4); `AlignmentResult`/`align` (Task 1) consumed by Task 4; `ProcessSummary` (dataclass, Task 4) is distinct from `ProcessResult` (Pydantic, Task 4) — the route maps one to the other; `is_anomaly` (Task 5) consumed by Task 5 route + Task 6 script; `NIMEmbedder.embed` (Task 3) consumed by `RealAIClient` (Task 4) and the sample script (Task 6). Signatures match across tasks.
