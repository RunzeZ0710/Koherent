# Week 2A — Retrieval Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Learning mode — "you drive, I coach".** The author is hand-writing this to
> learn. For each task the coach explains the concept and sketches the signature;
> the author writes the implementation; the coach reviews; tests confirm. The
> reference code in every step is the *target* — for the author-driven tasks
> (Task 3 `chunking`, Task 4 `alignment`) the author should attempt the function
> from the signature + explanation BEFORE reading the reference body.

**Goal:** A single call, `POST /lectures/{id}/process`, transcribes a lecture's
audio, slices the transcript into ~30s chunks, embeds every chunk and every
student note, and aligns each note to its best-matching transcript chunk (by
cosine similarity) — all persisted to Postgres.

**Architecture:** All AI work hides behind an `AIClient` interface (the "seam").
We build against a deterministic `FakeAIClient` now and add the real `NIMClient`
later by filling the same two methods. The pipeline is four small stages
(transcribe → chunk → embed → align) wired by a synchronous endpoint. Embeddings
are stored as Postgres `float[]` columns; cosine similarity is computed in Python
with numpy.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic, pydantic v2,
numpy, pytest, `uv`. Spec:
`docs/superpowers/specs/2026-05-30-week-2a-retrieval-pipeline-design.md`.

---

## File Structure

```
backend/
  pyproject.toml                          # MODIFY: add numpy
  src/koherent/
    ai/
      __init__.py                         # CREATE (empty)
      base.py                             # CREATE: AIClient Protocol
      fake.py                             # CREATE: FakeAIClient
      nim.py                              # CREATE: NIMClient stub (Task 6)
    pipeline/
      __init__.py                         # CREATE (empty)
      chunking.py                         # CREATE: chunk_transcript + ChunkText
      alignment.py                        # CREATE: cosine_similarity + best_chunk
      process.py                          # CREATE: process_lecture orchestrator
    models.py                             # MODIFY: Transcript, TranscriptChunk,
                                          #         NoteAlignment, Note.embedding
    schemas.py                            # MODIFY: ProcessResult
    deps.py                               # MODIFY: get_ai_client
    routes/processing.py                  # CREATE: POST /lectures/{id}/process
    main.py                               # MODIFY: mount processing router
  alembic/versions/0002_pipeline.py       # CREATE: schema migration
  tests/
    test_fake_ai.py                       # CREATE (Task 1)
    test_pipeline_models.py               # CREATE (Task 2)
    test_chunking.py                      # CREATE (Task 3)
    test_alignment.py                     # CREATE (Task 4)
    test_processing.py                    # CREATE (Task 5)
docs/wiki/                                # MODIFY (Task 7): topics + DECISIONS
```

---

## Task 1: The AIClient seam (Protocol + FakeAIClient)

**Files:**
- Modify: `backend/pyproject.toml` (add `numpy`)
- Create: `backend/src/koherent/ai/__init__.py` (empty)
- Create: `backend/src/koherent/ai/base.py`
- Create: `backend/src/koherent/ai/fake.py`
- Test: `backend/tests/test_fake_ai.py`

**Concept (coach):** A `Protocol` is Python's way of describing a *shape* — "any
object with these two methods counts as an `AIClient`" — without inheritance.
Our pipeline will depend on this shape, never on NVIDIA. `FakeAIClient` satisfies
the shape with deterministic, network-free behavior so we can build and test the
whole pipeline today. The embedding is a "bag of words" vector: we hash each word
into one of 64 buckets and count — so identical text gives identical vectors, and
text sharing words gives vectors that point in similar directions (high cosine).
We use `hashlib.md5`, not Python's built-in `hash()`, because `hash()` is
randomized per process and would break determinism across runs.

- [ ] **Step 1: Add numpy to dependencies**

In `backend/pyproject.toml`, change the `dependencies` list to add numpy:

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy>=2.0.36",
    "alembic>=1.14",
    "psycopg[binary]>=3.2",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "python-multipart>=0.0.17",
    "numpy>=2.0",
]
```

Then install:

```bash
cd backend && uv sync --extra dev
```

Expected: `uv` resolves and installs numpy.

- [ ] **Step 2: Create the `ai` package and the Protocol**

Create `backend/src/koherent/ai/__init__.py` (empty file).

Create `backend/src/koherent/ai/base.py`:

```python
from typing import Protocol


class AIClient(Protocol):
    """The seam between Koherent and any AI backend.

    The pipeline depends only on this shape. FakeAIClient implements it for
    development/tests; NIMClient implements it against NVIDIA NIM later.
    """

    def transcribe(self, audio_path: str) -> str:
        """Return the transcript text for the audio file at `audio_path`."""
        ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text, in the same order."""
        ...
```

- [ ] **Step 3: Write the failing test for FakeAIClient**

Create `backend/tests/test_fake_ai.py`:

```python
from koherent.ai.fake import FakeAIClient


def test_embed_is_deterministic_and_correct_length():
    ai = FakeAIClient()
    a = ai.embed(["marginal cost equals marginal revenue"])
    b = ai.embed(["marginal cost equals marginal revenue"])
    assert a == b                      # deterministic
    assert len(a) == 1                 # one vector per input
    assert len(a[0]) == FakeAIClient.DIM


def test_embed_shared_words_point_more_similarly_than_disjoint():
    import numpy as np

    ai = FakeAIClient()
    base, overlap, disjoint = ai.embed(
        ["supply and demand equilibrium", "supply and demand curve", "zebra igloo"]
    )

    def cos(x, y):
        x, y = np.array(x), np.array(y)
        return float(x.dot(y) / (np.linalg.norm(x) * np.linalg.norm(y)))

    assert cos(base, overlap) > cos(base, disjoint)


def test_transcribe_returns_text():
    ai = FakeAIClient()
    assert isinstance(ai.transcribe("anything.webm"), str)
    assert len(ai.transcribe("anything.webm")) > 0


def test_transcribe_can_be_overridden():
    ai = FakeAIClient(transcript="custom lecture text")
    assert ai.transcribe("ignored.webm") == "custom lecture text"
```

- [ ] **Step 4: Run the test and watch it fail**

Run:
```bash
cd backend && uv run pytest tests/test_fake_ai.py -v
```

Expected: FAIL — `ModuleNotFoundError: koherent.ai.fake`.

- [ ] **Step 5: Implement FakeAIClient**

Create `backend/src/koherent/ai/fake.py`:

```python
import hashlib

DEFAULT_TRANSCRIPT = (
    "Today we covered supply and demand. The market reaches equilibrium where "
    "the supply curve crosses the demand curve. A firm maximizes profit where "
    "marginal revenue equals marginal cost. A price floor set above equilibrium "
    "creates a surplus."
)


class FakeAIClient:
    """Deterministic, network-free AIClient for development and tests.

    `embed` is a hashed bag-of-words: each word is hashed (md5, for
    cross-run determinism) into one of DIM buckets and counted. Identical text
    yields identical vectors; shared words yield similar directions.
    """

    DIM = 64

    def __init__(self, transcript: str = DEFAULT_TRANSCRIPT) -> None:
        self._transcript = transcript

    def transcribe(self, audio_path: str) -> str:
        return self._transcript

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.DIM
        for word in text.lower().split():
            bucket = int(hashlib.md5(word.encode()).hexdigest(), 16) % self.DIM
            vec[bucket] += 1.0
        return vec
```

- [ ] **Step 6: Run the test and watch it pass**

Run:
```bash
cd backend && uv run pytest tests/test_fake_ai.py -v
```

Expected: `4 passed`.

- [ ] **Step 7: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/src/koherent/ai backend/tests/test_fake_ai.py
git commit -m "feat(ai): add AIClient seam with deterministic FakeAIClient"
```

---

## Task 2: Data model + migration (transcripts, chunks, alignments)

**Files:**
- Modify: `backend/src/koherent/models.py`
- Create: `backend/alembic/versions/0002_pipeline.py`
- Test: `backend/tests/test_pipeline_models.py`

**Concept (coach):** Three new tables plus one new column on `notes`. Embeddings
are `ARRAY(Float)` — a Postgres `float[]`. `note_alignments` is its own table
(not columns on `notes`) because alignment is a *derived* result we rebuild on
every reprocess; keeping it separate means reprocessing never touches raw notes.
Foreign keys use `ondelete=CASCADE` so deleting a transcript removes its chunks,
and removing a chunk removes any alignment pointing at it — which makes
reprocessing a clean "delete the transcript, rebuild" operation.

- [ ] **Step 1: Add the new models**

In `backend/src/koherent/models.py`, update the top imports to add `ARRAY`,
`Float`, and `Text`:

```python
from sqlalchemy import (
    ARRAY,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
```

Add an `embedding` column and an `alignment` relationship to the existing `Note`
class (place the column after `client_timestamp_ms` and the relationship after
the existing `lecture` relationship):

```python
    embedding: Mapped[list[float] | None] = mapped_column(ARRAY(Float), nullable=True)
```

```python
    alignment: Mapped["NoteAlignment | None"] = relationship(
        back_populates="note", cascade="all, delete-orphan", uselist=False
    )
```

Add a `transcript` relationship to the existing `Lecture` class (after its
`audio_recordings` relationship):

```python
    transcript: Mapped["Transcript | None"] = relationship(
        back_populates="lecture", cascade="all, delete-orphan", uselist=False
    )
```

Then append the three new model classes at the end of the file:

```python
class Transcript(Base):
    __tablename__ = "transcripts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    lecture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lectures.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lecture: Mapped[Lecture] = relationship(back_populates="transcript")
    chunks: Mapped[list["TranscriptChunk"]] = relationship(
        back_populates="transcript", cascade="all, delete-orphan"
    )


class TranscriptChunk(Base):
    __tablename__ = "transcript_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    transcript_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transcripts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    start_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    end_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    transcript: Mapped[Transcript] = relationship(back_populates="chunks")


class NoteAlignment(Base):
    __tablename__ = "note_alignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    note_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notes.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    transcript_chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transcript_chunks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    similarity: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    note: Mapped[Note] = relationship(back_populates="alignment")
    chunk: Mapped[TranscriptChunk] = relationship()
```

- [ ] **Step 2: Write the failing model test**

Create `backend/tests/test_pipeline_models.py`:

```python
import secrets

from koherent.models import (
    Class,
    Lecture,
    Note,
    NoteAlignment,
    Student,
    Transcript,
    TranscriptChunk,
)


def _seed_note(db) -> Note:
    klass = Class(name="Econ 101", join_code="ABC123", owner_token=secrets.token_urlsafe(32))
    db.add(klass)
    db.flush()
    student = Student(class_id=klass.id, display_name="Alice", session_token=secrets.token_urlsafe(32))
    lecture = Lecture(class_id=klass.id, title="Day 1")
    db.add_all([student, lecture])
    db.flush()
    note = Note(
        lecture_id=lecture.id, student_id=student.id, content="MR=MC", client_timestamp_ms=10
    )
    db.add(note)
    db.flush()
    return note


def test_transcript_chunk_and_alignment_persist(db):
    note = _seed_note(db)

    transcript = Transcript(lecture_id=note.lecture_id, full_text="full lecture text")
    db.add(transcript)
    db.flush()

    chunk = TranscriptChunk(
        transcript_id=transcript.id,
        chunk_index=0,
        content="marginal revenue equals marginal cost",
        start_ms=0,
        end_ms=30000,
        embedding=[0.1, 0.2, 0.3],
    )
    db.add(chunk)
    db.flush()

    note.embedding = [0.1, 0.2, 0.3]
    alignment = NoteAlignment(
        note_id=note.id, transcript_chunk_id=chunk.id, similarity=0.97
    )
    db.add(alignment)
    db.flush()

    refetched = db.get(NoteAlignment, alignment.id)
    assert refetched.similarity == 0.97
    assert refetched.chunk.content == "marginal revenue equals marginal cost"
    assert refetched.note.embedding == [0.1, 0.2, 0.3]


def test_deleting_transcript_cascades_to_chunks_and_alignments(db):
    note = _seed_note(db)
    transcript = Transcript(lecture_id=note.lecture_id, full_text="x")
    db.add(transcript)
    db.flush()
    chunk = TranscriptChunk(
        transcript_id=transcript.id, chunk_index=0, content="c", start_ms=0, end_ms=1, embedding=[1.0]
    )
    db.add(chunk)
    db.flush()
    db.add(NoteAlignment(note_id=note.id, transcript_chunk_id=chunk.id, similarity=0.5))
    db.flush()

    db.delete(transcript)
    db.flush()

    from sqlalchemy import func, select

    assert db.scalar(select(func.count(TranscriptChunk.id))) == 0
    assert db.scalar(select(func.count(NoteAlignment.id))) == 0
```

- [ ] **Step 3: Run the test and watch it fail**

Run:
```bash
cd backend && uv run pytest tests/test_pipeline_models.py -v
```

Expected: FAIL — `ImportError` (the new models don't exist) or, once models are
added, the test DB lacks tables. The `conftest.py` builds the test schema from
the models via `create_all`, so after Step 1 the import resolves; this run
confirms the models import and persist. If it fails on import before Step 1 is
saved, complete Step 1 first.

- [ ] **Step 4: Verify the model test passes against the test DB**

Run:
```bash
cd backend && uv run pytest tests/test_pipeline_models.py -v
```

Expected: `2 passed`. (The test DB is created from model metadata, so no
migration is needed for tests. The migration in the next steps is for the *dev*
database.)

- [ ] **Step 5: Write the migration for the dev database**

Create `backend/alembic/versions/0002_pipeline.py`:

```python
"""pipeline schema: transcripts, chunks, note embeddings, alignments

Revision ID: 0002
Revises: 0001
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("notes", sa.Column("embedding", sa.ARRAY(sa.Float()), nullable=True))

    op.create_table(
        "transcripts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("lecture_id", sa.UUID(), nullable=False),
        sa.Column("full_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["lecture_id"], ["lectures.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_transcripts_lecture_id"), "transcripts", ["lecture_id"], unique=True)

    op.create_table(
        "transcript_chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("transcript_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.BigInteger(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("start_ms", sa.BigInteger(), nullable=False),
        sa.Column("end_ms", sa.BigInteger(), nullable=False),
        sa.Column("embedding", sa.ARRAY(sa.Float()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["transcript_id"], ["transcripts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_transcript_chunks_transcript_id"), "transcript_chunks", ["transcript_id"], unique=False
    )

    op.create_table(
        "note_alignments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("note_id", sa.UUID(), nullable=False),
        sa.Column("transcript_chunk_id", sa.UUID(), nullable=False),
        sa.Column("similarity", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["note_id"], ["notes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transcript_chunk_id"], ["transcript_chunks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_note_alignments_note_id"), "note_alignments", ["note_id"], unique=True)
    op.create_index(
        op.f("ix_note_alignments_transcript_chunk_id"), "note_alignments", ["transcript_chunk_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_note_alignments_transcript_chunk_id"), table_name="note_alignments")
    op.drop_index(op.f("ix_note_alignments_note_id"), table_name="note_alignments")
    op.drop_table("note_alignments")
    op.drop_index(op.f("ix_transcript_chunks_transcript_id"), table_name="transcript_chunks")
    op.drop_table("transcript_chunks")
    op.drop_index(op.f("ix_transcripts_lecture_id"), table_name="transcripts")
    op.drop_table("transcripts")
    op.drop_column("notes", "embedding")
```

- [ ] **Step 6: Apply the migration to the dev DB**

Run:
```bash
cd backend && uv run alembic upgrade head
```

Expected: `Running upgrade 0001 -> 0002, pipeline schema ...`.

Verify the tables exist:
```bash
docker compose exec db psql -U koherent -d koherent -c '\dt'
```

Expected: lists `transcripts`, `transcript_chunks`, `note_alignments` alongside
the Week 1 tables.

- [ ] **Step 7: Commit**

```bash
git add backend/src/koherent/models.py backend/alembic/versions/0002_pipeline.py backend/tests/test_pipeline_models.py
git commit -m "feat(db): add transcript, chunk, note-embedding, alignment schema"
```

---

## Task 3: Transcript chunking (you drive)

**Files:**
- Create: `backend/src/koherent/pipeline/__init__.py` (empty)
- Create: `backend/src/koherent/pipeline/chunking.py`
- Test: `backend/tests/test_chunking.py`

**Concept (coach):** A transcript is one long string. To align notes to *moments*
in the lecture, we cut it into fixed-size pieces. We approximate "~30 seconds of
speech" as a fixed number of words (people speak ~2.5 words/sec, so ~75 words ≈
30s) and lay the chunks end-to-end on a 30-second grid. The real ASR will later
return true per-word timestamps we can use instead; for now this is an honest
approximation. Your job: split the words into groups of `words_per_chunk` and
stamp each group with `start_ms`/`end_ms`.

**Signature to implement (try it before reading the body below):**
```python
def chunk_transcript(
    full_text: str, words_per_chunk: int = 75, chunk_ms: int = 30_000
) -> list[ChunkText]: ...
```
where `ChunkText` has `index`, `content`, `start_ms`, `end_ms`. Empty/whitespace
input → empty list. Chunk `i` covers `words[i*wpc : (i+1)*wpc]`, with
`start_ms = i*chunk_ms` and `end_ms = (i+1)*chunk_ms`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_chunking.py`:

```python
from koherent.pipeline.chunking import ChunkText, chunk_transcript


def test_empty_text_yields_no_chunks():
    assert chunk_transcript("   ") == []


def test_single_chunk_when_under_limit():
    chunks = chunk_transcript("alpha beta gamma", words_per_chunk=75)
    assert len(chunks) == 1
    assert chunks[0] == ChunkText(index=0, content="alpha beta gamma", start_ms=0, end_ms=30_000)


def test_splits_into_fixed_word_groups_with_timestamps():
    text = "one two three four five"
    chunks = chunk_transcript(text, words_per_chunk=2, chunk_ms=30_000)
    assert len(chunks) == 3
    assert [c.content for c in chunks] == ["one two", "three four", "five"]
    assert [(c.index, c.start_ms, c.end_ms) for c in chunks] == [
        (0, 0, 30_000),
        (1, 30_000, 60_000),
        (2, 60_000, 90_000),
    ]
```

- [ ] **Step 2: Run the tests and watch them fail**

Run:
```bash
cd backend && uv run pytest tests/test_chunking.py -v
```

Expected: FAIL — `ModuleNotFoundError: koherent.pipeline.chunking`.

- [ ] **Step 3: Implement chunking (author writes; reference below)**

Create `backend/src/koherent/pipeline/__init__.py` (empty file).

Create `backend/src/koherent/pipeline/chunking.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkText:
    index: int
    content: str
    start_ms: int
    end_ms: int


def chunk_transcript(
    full_text: str, words_per_chunk: int = 75, chunk_ms: int = 30_000
) -> list[ChunkText]:
    """Split transcript text into fixed-size, time-stamped chunks.

    Approximates ~30s chunks by grouping a fixed number of words and laying
    them on a `chunk_ms` grid. Whitespace-only input yields no chunks.
    """
    words = full_text.split()
    chunks: list[ChunkText] = []
    for i in range(0, len(words), words_per_chunk):
        index = i // words_per_chunk
        content = " ".join(words[i : i + words_per_chunk])
        chunks.append(
            ChunkText(
                index=index,
                content=content,
                start_ms=index * chunk_ms,
                end_ms=(index + 1) * chunk_ms,
            )
        )
    return chunks
```

- [ ] **Step 4: Run the tests and watch them pass**

Run:
```bash
cd backend && uv run pytest tests/test_chunking.py -v
```

Expected: `3 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/src/koherent/pipeline/__init__.py backend/src/koherent/pipeline/chunking.py backend/tests/test_chunking.py
git commit -m "feat(pipeline): add fixed-size transcript chunking"
```

---

## Task 4: Cosine-similarity alignment (you drive — the centerpiece)

**Files:**
- Create: `backend/src/koherent/pipeline/alignment.py`
- Test: `backend/tests/test_alignment.py`

**Concept (coach):** An embedding is a point in high-dimensional space; texts with
similar meaning point in similar directions. **Cosine similarity** measures the
angle between two vectors: `dot(a,b) / (|a| · |b|)`. It's `1.0` for identical
directions, `0.0` for perpendicular (nothing in common). To align a note, we
compute its cosine similarity to every transcript chunk and keep the highest —
that's the moment the note best matches. Edge case: a zero vector has no
direction, so define its similarity as `0.0` (and avoid dividing by zero).

**Signatures to implement (try before reading the body):**
```python
def cosine_similarity(a: list[float], b: list[float]) -> float: ...

@dataclass(frozen=True)
class Match:
    chunk_id: Any
    similarity: float

def best_chunk(
    note_embedding: list[float], chunks: list[tuple[Any, list[float]]]
) -> Match | None: ...   # None if there are no chunks
```

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_alignment.py`:

```python
import pytest

from koherent.pipeline.alignment import Match, best_chunk, cosine_similarity


def test_identical_vectors_have_similarity_one():
    assert cosine_similarity([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_perpendicular_vectors_have_similarity_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_zero_vector_is_zero_not_error():
    assert cosine_similarity([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_best_chunk_picks_the_closest():
    # note points in nearly the same direction as "c"; clearly not "a" or "b".
    chunks = [
        ("a", [1.0, 0.0]),
        ("b", [0.0, 1.0]),
        ("c", [0.6, 0.8]),
    ]
    match = best_chunk([0.5, 0.86], chunks)
    assert isinstance(match, Match)
    assert match.chunk_id == "c"
    assert match.similarity > 0.9


def test_best_chunk_returns_none_when_no_chunks():
    assert best_chunk([1.0, 0.0], []) is None
```

- [ ] **Step 2: Run the tests and watch them fail**

Run:
```bash
cd backend && uv run pytest tests/test_alignment.py -v
```

Expected: FAIL — `ModuleNotFoundError: koherent.pipeline.alignment`.

- [ ] **Step 3: Implement alignment (author writes; reference below)**

Create `backend/src/koherent/pipeline/alignment.py`:

```python
from dataclasses import dataclass
from typing import Any

import numpy as np


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine of the angle between two vectors. 0.0 if either is a zero vector."""
    va = np.array(a, dtype=float)
    vb = np.array(b, dtype=float)
    na = float(np.linalg.norm(va))
    nb = float(np.linalg.norm(vb))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(va.dot(vb) / (na * nb))


@dataclass(frozen=True)
class Match:
    chunk_id: Any
    similarity: float


def best_chunk(
    note_embedding: list[float], chunks: list[tuple[Any, list[float]]]
) -> Match | None:
    """Return the (chunk_id, similarity) of the chunk most similar to the note,
    or None if there are no chunks."""
    best: Match | None = None
    for chunk_id, chunk_embedding in chunks:
        sim = cosine_similarity(note_embedding, chunk_embedding)
        if best is None or sim > best.similarity:
            best = Match(chunk_id=chunk_id, similarity=sim)
    return best
```

- [ ] **Step 4: Run the tests and watch them pass**

Run:
```bash
cd backend && uv run pytest tests/test_alignment.py -v
```

Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/src/koherent/pipeline/alignment.py backend/tests/test_alignment.py
git commit -m "feat(pipeline): add cosine-similarity note-to-chunk alignment"
```

---

## Task 5: Orchestrator + `POST /lectures/{id}/process`

**Files:**
- Modify: `backend/src/koherent/deps.py` (add `get_ai_client`)
- Modify: `backend/src/koherent/schemas.py` (add `ProcessResult`)
- Create: `backend/src/koherent/pipeline/process.py`
- Create: `backend/src/koherent/routes/processing.py`
- Modify: `backend/src/koherent/main.py` (mount router)
- Test: `backend/tests/test_processing.py`

**Concept (coach):** Now we wire the four stages. `process_lecture` is pure
orchestration — it calls `ai.transcribe`, `chunk_transcript`, `ai.embed`, and
`best_chunk`, and writes rows. It contains no clever logic of its own (all the
logic lives in the units we already tested). Reprocessing is idempotent: we delete
the existing transcript first, which cascades to its chunks and their alignments,
then rebuild. The `AIClient` is injected via `get_ai_client` (same pattern as
`get_db`), so the test forces a `FakeAIClient` with a known transcript.

- [ ] **Step 1: Add the `get_ai_client` dependency**

In `backend/src/koherent/deps.py`, add these imports at the top (alongside the
existing imports):

```python
from koherent.ai.base import AIClient
from koherent.ai.fake import FakeAIClient
```

And add this function at the end of the file:

```python
def get_ai_client() -> AIClient:
    # V1: deterministic fake. Swap for NIMClient (Task 6) when an nvapi key exists.
    return FakeAIClient()
```

- [ ] **Step 2: Add the `ProcessResult` schema**

Append to `backend/src/koherent/schemas.py`:

```python
class ProcessResult(BaseModel):
    lecture_id: uuid.UUID
    transcript_id: uuid.UUID
    chunk_count: int
    aligned_note_count: int
```

- [ ] **Step 3: Write the orchestrator**

Create `backend/src/koherent/pipeline/process.py`:

```python
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from koherent.ai.base import AIClient
from koherent.models import AudioRecording, Lecture, Note, NoteAlignment, Transcript, TranscriptChunk
from koherent.pipeline.alignment import best_chunk
from koherent.pipeline.chunking import chunk_transcript
from koherent.storage import storage_root


class NoAudioError(Exception):
    """Raised when a lecture has no audio recording to process."""


def process_lecture(lecture: Lecture, db: Session, ai: AIClient) -> Transcript:
    """Run the retrieval pipeline for one lecture: transcribe -> chunk ->
    embed -> align. Idempotent: clears any prior transcript (cascading to its
    chunks and alignments) and rebuilds. Returns the new Transcript."""
    audio = db.scalar(
        select(AudioRecording)
        .where(AudioRecording.lecture_id == lecture.id)
        .order_by(AudioRecording.created_at)
    )
    if audio is None:
        raise NoAudioError(f"Lecture {lecture.id} has no audio to process")

    # Idempotency: deleting the transcript cascades to chunks and (via the
    # chunk FK) to alignments. Also clear note embeddings so a re-run is clean.
    existing = db.scalar(select(Transcript).where(Transcript.lecture_id == lecture.id))
    if existing is not None:
        db.delete(existing)
        db.flush()
    notes = list(db.scalars(select(Note).where(Note.lecture_id == lecture.id)))
    for note in notes:
        note.embedding = None
    db.flush()

    # 1. Transcribe
    audio_path = str(storage_root() / audio.file_path)
    text = ai.transcribe(audio_path)
    transcript = Transcript(lecture_id=lecture.id, full_text=text)
    db.add(transcript)
    db.flush()

    # 2. Chunk
    chunk_texts = chunk_transcript(text)

    # 3. Embed chunks and notes
    chunk_vectors = ai.embed([c.content for c in chunk_texts]) if chunk_texts else []
    chunk_rows: list[TranscriptChunk] = []
    for ct, vec in zip(chunk_texts, chunk_vectors):
        row = TranscriptChunk(
            transcript_id=transcript.id,
            chunk_index=ct.index,
            content=ct.content,
            start_ms=ct.start_ms,
            end_ms=ct.end_ms,
            embedding=vec,
        )
        db.add(row)
        chunk_rows.append(row)
    db.flush()

    if notes:
        note_vectors = ai.embed([n.content for n in notes])
        for note, vec in zip(notes, note_vectors):
            note.embedding = vec

    # 4. Align each note to its best chunk
    candidates = [(row.id, row.embedding) for row in chunk_rows]
    for note in notes:
        if note.embedding is None or not candidates:
            continue
        match = best_chunk(note.embedding, candidates)
        if match is not None:
            db.add(
                NoteAlignment(
                    note_id=note.id,
                    transcript_chunk_id=match.chunk_id,
                    similarity=match.similarity,
                )
            )

    db.commit()
    db.refresh(transcript)
    return transcript
```

- [ ] **Step 4: Create the route**

Create `backend/src/koherent/routes/processing.py`:

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from koherent.ai.base import AIClient
from koherent.deps import get_ai_client, get_current_student, get_db
from koherent.models import Note, NoteAlignment, Student, TranscriptChunk
from koherent.pipeline.process import NoAudioError, process_lecture
from koherent.routes.lectures import _load_lecture_for_student
from koherent.schemas import ProcessResult

router = APIRouter(prefix="/lectures", tags=["processing"])


@router.post("/{lecture_id}/process", response_model=ProcessResult)
def process(
    lecture_id: uuid.UUID,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
    ai: AIClient = Depends(get_ai_client),
) -> ProcessResult:
    lecture = _load_lecture_for_student(lecture_id, current, db)
    try:
        transcript = process_lecture(lecture, db, ai)
    except NoAudioError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    chunk_count = db.scalar(
        select(func.count(TranscriptChunk.id)).where(
            TranscriptChunk.transcript_id == transcript.id
        )
    ) or 0
    aligned_note_count = db.scalar(
        select(func.count(NoteAlignment.id))
        .join(Note, Note.id == NoteAlignment.note_id)
        .where(Note.lecture_id == lecture.id)
    ) or 0

    return ProcessResult(
        lecture_id=lecture.id,
        transcript_id=transcript.id,
        chunk_count=chunk_count,
        aligned_note_count=aligned_note_count,
    )
```

- [ ] **Step 5: Mount the router**

In `backend/src/koherent/main.py`, update the routes import and add the mount.

Change:
```python
from koherent.routes import classes, lectures
```
to:
```python
from koherent.routes import classes, lectures, processing
```

And after `app.include_router(lectures.router)` add:
```python
app.include_router(processing.router)
```

- [ ] **Step 6: Write the integration test**

Create `backend/tests/test_processing.py`:

```python
import io

import pytest

from koherent.ai.fake import FakeAIClient
from koherent.deps import get_ai_client
from koherent.main import app
from koherent.models import Note, NoteAlignment, Transcript, TranscriptChunk


def _join_and_start(client):
    klass = client.post("/classes", json={"name": "Econ 101"}).json()
    client.post(
        "/classes/join",
        json={"join_code": klass["join_code"], "display_name": "Alice"},
    )
    return client.post("/lectures", json={"title": "Day 1"}).json()


def _override_ai(transcript: str):
    def _factory():
        return FakeAIClient(transcript=transcript)

    return _factory


def test_process_without_audio_returns_409(client):
    lecture = _join_and_start(client)
    resp = client.post(f"/lectures/{lecture['id']}/process")
    assert resp.status_code == 409


def test_process_builds_transcript_chunks_and_alignments(client, db):
    # Known transcript with four distinct words -> one chunk "alpha beta gamma delta".
    app.dependency_overrides[get_ai_client] = _override_ai("alpha beta gamma delta")
    try:
        lecture = _join_and_start(client)
        # One note identical to the chunk (should score ~1.0), one unrelated.
        client.post(
            f"/lectures/{lecture['id']}/notes",
            json={"content": "alpha beta gamma delta", "client_timestamp_ms": 1000},
        )
        client.post(
            f"/lectures/{lecture['id']}/notes",
            json={"content": "kangaroo", "client_timestamp_ms": 2000},
        )
        # Upload a (fake) audio file so processing has something to transcribe.
        client.post(
            f"/lectures/{lecture['id']}/audio",
            files={"file": ("lecture.webm", io.BytesIO(b"fake-bytes" * 50), "audio/webm")},
        )

        resp = client.post(f"/lectures/{lecture['id']}/process")
        assert resp.status_code == 200
        body = resp.json()
        assert body["chunk_count"] == 1
        assert body["aligned_note_count"] == 2

        # Verify persistence directly.
        from sqlalchemy import select

        transcript = db.scalar(select(Transcript).where(Transcript.lecture_id == lecture["id"]))
        assert transcript is not None and transcript.full_text == "alpha beta gamma delta"
        assert db.scalar(select(TranscriptChunk).where(TranscriptChunk.transcript_id == transcript.id)) is not None

        # The identical note should align with the highest possible similarity.
        notes = {n.content: n for n in db.scalars(select(Note).where(Note.lecture_id == lecture["id"]))}
        identical = db.scalar(select(NoteAlignment).where(NoteAlignment.note_id == notes["alpha beta gamma delta"].id))
        unrelated = db.scalar(select(NoteAlignment).where(NoteAlignment.note_id == notes["kangaroo"].id))
        assert identical.similarity == pytest.approx(1.0)
        assert identical.similarity > unrelated.similarity
    finally:
        app.dependency_overrides.pop(get_ai_client, None)


def test_process_is_idempotent(client, db):
    app.dependency_overrides[get_ai_client] = _override_ai("alpha beta gamma delta")
    try:
        lecture = _join_and_start(client)
        client.post(
            f"/lectures/{lecture['id']}/notes",
            json={"content": "alpha beta", "client_timestamp_ms": 1000},
        )
        client.post(
            f"/lectures/{lecture['id']}/audio",
            files={"file": ("lecture.webm", io.BytesIO(b"x" * 50), "audio/webm")},
        )
        first = client.post(f"/lectures/{lecture['id']}/process").json()
        second = client.post(f"/lectures/{lecture['id']}/process").json()

        from sqlalchemy import func, select

        # Exactly one transcript and one alignment per note after two runs.
        assert db.scalar(select(func.count(Transcript.id)).where(Transcript.lecture_id == lecture["id"])) == 1
        assert second["aligned_note_count"] == first["aligned_note_count"] == 1
    finally:
        app.dependency_overrides.pop(get_ai_client, None)
```

- [ ] **Step 7: Run the processing tests and watch them pass**

Run:
```bash
cd backend && uv run pytest tests/test_processing.py -v
```

Expected: `3 passed`.

- [ ] **Step 8: Run the full suite**

Run:
```bash
cd backend && uv run pytest
```

Expected: all tests pass (Week 1 + Week 2A).

- [ ] **Step 9: Commit**

```bash
git add backend/src/koherent/deps.py backend/src/koherent/schemas.py \
        backend/src/koherent/pipeline/process.py backend/src/koherent/routes/processing.py \
        backend/src/koherent/main.py backend/tests/test_processing.py
git commit -m "feat(pipeline): add synchronous POST /lectures/{id}/process"
```

---

## Task 6: NIMClient stub (prove the seam)

**Files:**
- Create: `backend/src/koherent/ai/nim.py`
- Test: `backend/tests/test_fake_ai.py` (append one test)

**Concept (coach):** This proves the seam works: a second implementation of the
same `AIClient` shape. It's an intentional stub — the bodies raise
`NotImplementedError` with a note on what goes in when the `nvapi-…` key exists.
Writing it now means the V1→V2 switch later is "fill two methods + change one
line in `get_ai_client`", nothing more.

- [ ] **Step 1: Write the stub**

Create `backend/src/koherent/ai/nim.py`:

```python
from koherent.config import settings


class NIMClient:
    """Real AIClient backed by NVIDIA NIM endpoints. STUB.

    Fill these in when an `nvapi-...` key exists:
      - transcribe(): POST the audio to the NIM ASR endpoint (Nemotron Speech /
        Riva) and return the transcript text.
      - embed(): call the NIM embeddings model (nvidia/nv-embedqa-e5-v5) with the
        batch of texts and return one vector per text.
    The OpenAI-compatible client (base_url=https://integrate.api.nvidia.com/v1)
    covers chat + embeddings; ASR uses a separate speech endpoint.
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self._api_key = api_key
        self._base_url = base_url or "https://integrate.api.nvidia.com/v1"

    def transcribe(self, audio_path: str) -> str:
        raise NotImplementedError("NIMClient.transcribe: wire up NIM ASR when a key exists")

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError("NIMClient.embed: wire up nv-embedqa-e5-v5 when a key exists")
```

- [ ] **Step 2: Append a test asserting it satisfies the interface but is unimplemented**

Append to `backend/tests/test_fake_ai.py`:

```python
def test_nim_client_satisfies_interface_but_is_stubbed():
    import pytest

    from koherent.ai.base import AIClient
    from koherent.ai.nim import NIMClient

    nim: AIClient = NIMClient(api_key="nvapi-fake")  # type-checks as an AIClient
    with pytest.raises(NotImplementedError):
        nim.transcribe("x.webm")
    with pytest.raises(NotImplementedError):
        nim.embed(["x"])
```

- [ ] **Step 3: Run and watch it pass**

Run:
```bash
cd backend && uv run pytest tests/test_fake_ai.py -v
```

Expected: `5 passed` (4 from Task 1 + this one).

- [ ] **Step 4: Commit**

```bash
git add backend/src/koherent/ai/nim.py backend/tests/test_fake_ai.py
git commit -m "feat(ai): add NIMClient stub to prove the AIClient seam"
```

---

## Task 7: Document the decisions in the wiki

**Files:**
- Create: `docs/wiki/topics/07-ai-pipeline.md`
- Modify: `docs/wiki/DECISIONS.md`

**Concept (coach):** Same framework as the Week 1 wiki — record *why* behind each
new decision so the wiki stays the source of truth. We add one topic page and the
index rows. New decisions: the AIClient seam, fake-first development, synchronous
processing, float[]+Python similarity, fixed-size chunking, alignment in its own
table.

- [ ] **Step 1: Write the topic page**

Create `docs/wiki/topics/07-ai-pipeline.md`:

```markdown
# 07 — The AI Retrieval Pipeline (Week 2A)

> **Decisions on this page:** D-023, D-024, D-025, D-026, D-027, D-028

---

## 1. The concept from zero

After a lecture we have two things: an audio recording and a pile of typed
student notes. The retrieval pipeline turns the audio into searchable text and
then figures out, for each note, *which moment of the lecture it corresponds to*.

Four stages:

1. **Transcribe** — speech-to-text (ASR) turns the audio into a transcript.
2. **Chunk** — the transcript is sliced into ~30-second pieces, so we can talk
   about "the part of the lecture around minute 12" instead of one giant blob.
3. **Embed** — each chunk and each note is turned into an *embedding*: a list of
   numbers (a vector) that captures its meaning. Texts with similar meaning get
   vectors pointing in similar directions.
4. **Align** — for each note, we find the transcript chunk whose embedding is
   most similar (by **cosine similarity** — the angle between the two vectors).
   That's the moment the note best matches.

The output: every note is linked to its best-matching chunk, with a similarity
score. That linkage is the foundation Week 2B builds on (judging whether the note
captured that moment *correctly*).

## 2. What we chose

- **An `AIClient` seam.** All AI work hides behind one interface with two methods
  (`transcribe`, `embed`). The pipeline depends only on this interface.
- **Fake-first development.** We built and tested everything against a
  deterministic `FakeAIClient` (no network, no API key), with a `NIMClient` stub
  ready to fill in. See `backend/src/koherent/ai/`.
- **Synchronous processing.** `POST /lectures/{id}/process` runs all four stages
  inline and returns when done. Idempotent: re-running clears and rebuilds.
- **`float[]` columns + cosine similarity in Python (numpy).** Embeddings are
  stored as plain Postgres arrays; the math runs in our code.
- **Fixed-size chunking** (~75 words ≈ 30s) on a 30-second grid.
- **Alignment in its own table** (`note_alignments`), separate from raw notes.

## 3. What we rejected, and why

- **Calling NVIDIA directly from the pipeline.** Would couple every stage to one
  vendor and block all work until a key existed. The seam lets us build now and
  swap the real client in later by filling two methods — which is also the
  project's V1→V2 migration story, made literally true.
- **`pgvector` for vector storage/search.** More production-grade and scales to
  millions of vectors, but adds a DB extension and hides the similarity math in
  SQL operators. At our scale (≤30 students × a few hundred vectors), `float[]`
  + numpy is ample and keeps the math visible. Migrating to `pgvector` later is
  itself a good engineering story.
- **A background job queue.** More realistic for "results in 2–5 minutes," but a
  lot of moving parts (worker, queue, status polling) to hand-write now. The fake
  client is instant; a synchronous endpoint is trivial to test and reason about.
- **Storing the alignment as columns on `notes`.** Alignment is derived and
  rebuilt on reprocess; a separate table keeps raw input and derived output
  cleanly split.
- **Topic-shift / semantic chunking.** Smarter boundaries, but premature.
  `project_plan.md` calls for fixed 30s chunks first; refine only if alignment is
  too noisy.

## 4. In our code

| Thing | Where |
|-------|-------|
| The seam (Protocol) | `backend/src/koherent/ai/base.py` |
| FakeAIClient (deterministic) | `backend/src/koherent/ai/fake.py` |
| NIMClient (stub) | `backend/src/koherent/ai/nim.py` |
| Chunking | `backend/src/koherent/pipeline/chunking.py` |
| Cosine similarity + alignment | `backend/src/koherent/pipeline/alignment.py` |
| Orchestrator | `backend/src/koherent/pipeline/process.py` |
| Endpoint | `backend/src/koherent/routes/processing.py` |
| Schema (transcripts/chunks/alignments) | `backend/src/koherent/models.py`, migration `0002` |

## 5. Decision records

### D-023: Hide all AI work behind an AIClient seam

- **Date:** 2026-05-30
- **Status:** Active
- **Context:** The pipeline needs ASR + embeddings, but we have no NVIDIA key
  yet and don't want to couple the pipeline to one vendor.
- **Decision:** Define an `AIClient` Protocol (`transcribe`, `embed`); depend only
  on it; provide `FakeAIClient` now and `NIMClient` later.
- **Why:** Unblocks all pipeline work without a key; isolates the vendor; makes
  the V1→V2 migration a two-method swap behind a stable interface.
- **Alternatives rejected:** Calling NVIDIA directly (vendor lock-in, blocks work
  until a key exists).

### D-024: Develop fake-first (deterministic FakeAIClient)

- **Date:** 2026-05-30
- **Status:** Active
- **Context:** We need to build and test the pipeline before a key exists, with
  predictable results.
- **Decision:** Build against a deterministic `FakeAIClient` (hashed bag-of-words
  embeddings, canned transcript), injected via FastAPI dependency override in
  tests.
- **Why:** No network/flakiness; predictable similarities let tests assert exact
  alignments; the real client drops in behind the same seam.
- **Alternatives rejected:** Waiting for a key (blocked); mocking per-test (less
  reusable than one fake behind the interface).

### D-025: Synchronous processing endpoint

- **Date:** 2026-05-30
- **Status:** Active
- **Context:** Something must trigger the pipeline when a lecture is done.
- **Decision:** `POST /lectures/{id}/process` runs all stages inline and returns
  when finished; re-running is idempotent (clear + rebuild).
- **Why:** Simple to write, test, and reason about; the fake client is instant.
- **Alternatives rejected:** Background job + queue + status polling (many moving
  parts, premature now).

### D-026: Store embeddings as float[] and compute similarity in Python

- **Date:** 2026-05-30
- **Status:** Active
- **Context:** Embeddings are ~1024-float vectors that must be compared.
- **Decision:** Store as Postgres `ARRAY(Float)`; compute cosine similarity in
  Python with numpy.
- **Why:** Zero new infrastructure; the math stays visible and hand-writable;
  ample at our scale.
- **Alternatives rejected:** `pgvector` (extra extension, hides the math; revisit
  at scale — a good future migration story).

### D-027: Fixed-size transcript chunking

- **Date:** 2026-05-30
- **Status:** Active
- **Context:** The transcript must be split into alignable pieces.
- **Decision:** Fixed ~75-word chunks laid on a 30-second grid.
- **Why:** Matches the plan's "fixed 30s chunks first"; simple and testable; real
  ASR word timestamps can refine it later.
- **Alternatives rejected:** Topic-shift/semantic chunking (premature; only if
  alignment proves too noisy).

### D-028: Alignment stored in its own table

- **Date:** 2026-05-30
- **Status:** Active
- **Context:** Alignment is a derived result recomputed on every reprocess.
- **Decision:** Store it in `note_alignments` (one row per note), not as columns
  on `notes`.
- **Why:** Reprocessing rebuilds derived data without touching raw notes; clean
  separation of input and output.
- **Alternatives rejected:** Columns on `notes` (mixes raw and derived; messier
  reprocess).
```

- [ ] **Step 2: Add the index rows**

In `docs/wiki/DECISIONS.md`, add these rows to the end of the table (before the
"Status legend" section):

```markdown
| [D-023](topics/07-ai-pipeline.md#d-023-hide-all-ai-work-behind-an-aiclient-seam) | Hide all AI work behind an AIClient seam | 2026-05-30 | Active | [07-ai-pipeline](topics/07-ai-pipeline.md) |
| [D-024](topics/07-ai-pipeline.md#d-024-develop-fake-first-deterministic-fakeaiclient) | Develop fake-first with a deterministic FakeAIClient | 2026-05-30 | Active | [07-ai-pipeline](topics/07-ai-pipeline.md) |
| [D-025](topics/07-ai-pipeline.md#d-025-synchronous-processing-endpoint) | Synchronous POST /lectures/{id}/process | 2026-05-30 | Active | [07-ai-pipeline](topics/07-ai-pipeline.md) |
| [D-026](topics/07-ai-pipeline.md#d-026-store-embeddings-as-float-and-compute-similarity-in-python) | Store embeddings as float[]; cosine similarity in Python | 2026-05-30 | Active | [07-ai-pipeline](topics/07-ai-pipeline.md) |
| [D-027](topics/07-ai-pipeline.md#d-027-fixed-size-transcript-chunking) | Fixed-size (~30s) transcript chunking | 2026-05-30 | Active | [07-ai-pipeline](topics/07-ai-pipeline.md) |
| [D-028](topics/07-ai-pipeline.md#d-028-alignment-stored-in-its-own-table) | Alignment stored in its own note_alignments table | 2026-05-30 | Active | [07-ai-pipeline](topics/07-ai-pipeline.md) |
```

- [ ] **Step 3: Commit**

```bash
git add docs/wiki/topics/07-ai-pipeline.md docs/wiki/DECISIONS.md
git commit -m "docs(wiki): document Week 2A AI pipeline decisions (D-023..D-028)"
```

---

## Final verification

- [ ] **Step 1: Full backend suite passes**

Run:
```bash
cd backend && uv run pytest -v
```

Expected: all tests pass — Week 1 (18) plus Week 2A
(`test_fake_ai` 5, `test_pipeline_models` 2, `test_chunking` 3, `test_alignment`
5, `test_processing` 3).

- [ ] **Step 2: Confirm the dev DB is migrated**

Run:
```bash
cd backend && uv run alembic current
```

Expected: `0002 (head)`.

---

## What's deferred to Week 2B

- Claim extraction from notes (LLM)
- LLM-as-judge: did the note capture the chunk's concept *correctly*?
- Per-student feedback report generation

These build directly on the note→chunk alignments produced here.
```