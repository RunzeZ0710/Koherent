# Generative + Eval Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add LLM generation, course-material ingestion, top-k retrieval, four grounded assistant endpoints, and an evaluation harness to the existing Koherent pipeline, per `docs/superpowers/specs/2026-07-08-generative-eval-layer-design.md`.

**Architecture:** Everything plugs into the existing `AIClient` seam (protocol in `ai/base.py`, fake in `ai/fake.py`, real NVIDIA adapters composed in `ai/real.py`). New pure pipeline modules (text chunking, extraction, retrieval, prompts, judge) follow the existing pattern: pure functions, DB-free, unit-tested with hand-made data. Routes follow the existing router-per-resource + DI pattern. All tests run offline against `FakeAIClient` and a real Postgres test DB.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0, Alembic, Postgres (docker, port 5433), NVIDIA NIM (embeddings `nvidia/nv-embedqa-e5-v5`, chat `meta/llama-3.3-70b-instruct`) via OpenAI SDK, NVIDIA Riva ASR, pypdf (new dep), pytest.

## Global Constraints

- Work from `backend/`; run everything with `uv run <cmd>` (e.g. `uv run pytest`, `uv run ruff check src tests`).
- Postgres must be up: `docker compose up -d` from the repo root (serves port 5433).
- **Parallel test isolation:** when running as a parallel subagent, DB-backed tests MUST use a dedicated test database. Create it once, then export the URL for every pytest run:
  ```bash
  PGPASSWORD=koherent psql -h localhost -p 5433 -U koherent -d koherent -c "CREATE DATABASE koherent_test_taskN;" || true
  export TEST_DATABASE_URL="postgresql+psycopg://koherent:koherent@localhost:5433/koherent_test_taskN"
  ```
  (replace `taskN` with your task number). Pure tests (no `client`/`db` fixture) need no DB.
- Strict TDD: write the failing test, watch it fail, implement, watch it pass. `FakeAIClient` for all tests — **no network calls in tests, ever**.
- Ruff: line length 100, target py311. Run `uv run ruff check src tests` before finishing.
- **Commits (parallel mode):** subagents do NOT run `git add`/`git commit` — the orchestrator commits each task's files at wave boundaries after the integrated full suite passes. (Commit steps below are executed by the orchestrator.)
- Only new dependency allowed: `pypdf>=5` (Task 3). Do not add anything else.
- NVIDIA endpoint for all NIM calls: `https://integrate.api.nvidia.com/v1`; chat model comes from the `nim_chat_model` setting, never hardcoded at call sites.
- Match existing docstring style: module docstrings explain *why*, code stays comment-light.

## File Ownership Map (conflict avoidance for parallel execution)

| File | Sole owner |
|---|---|
| `src/koherent/ai/base.py`, `ai/fake.py` | Task 1 |
| `src/koherent/pipeline/text_chunking.py` | Task 2 |
| `src/koherent/pipeline/extraction.py`, `pyproject.toml` (deps) | Task 3 |
| `src/koherent/pipeline/retrieval.py`, `ai/embeddings.py` | Task 4 |
| `src/koherent/models.py`, `alembic/versions/0003_materials.py` | Task 5 |
| `src/koherent/routes/access.py`, `routes/processing.py`, `routes/lectures.py` | Task 6 |
| `src/koherent/ai/chat.py`, `ai/real.py`, `config.py` | Task 7 |
| `src/koherent/pipeline/prompts.py` | Task 8 |
| `src/koherent/pipeline/judge.py` | Task 9 |
| `src/koherent/schemas.py`, `main.py`, route-file skeletons | Task 10 |
| `src/koherent/routes/materials.py` (body) | Task 11 |
| `src/koherent/routes/assistant.py` (body) | Task 12 |
| `src/koherent/routes/study.py` (body) | Task 13 |
| `src/koherent/pipeline/metrics.py`, `evals/*`, `pyproject.toml` (pytest pythonpath) | Task 14 |
| `docs/wiki/*`, `README.md`, `project_plan.md` | Task 15 |

## Wave Schedule

- **Wave 1 (parallel):** Tasks 1, 2, 3, 4, 5, 6
- **Wave 2 (parallel, after wave 1):** Tasks 7, 8, 9, 10
- **Wave 3 (parallel, after wave 2):** Tasks 11, 12, 13
- **Wave 4 (after wave 3):** Task 14
- **Wave 5 (after wave 4):** Task 15

---

### Task 1: Extend the AI seam — `generate()` and `embed_query()`

**Files:**
- Modify: `backend/src/koherent/ai/base.py`
- Modify: `backend/src/koherent/ai/fake.py`
- Test: `backend/tests/test_fake_ai.py` (append)

**Interfaces:**
- Consumes: nothing new.
- Produces (later tasks rely on these exact signatures):
  - `AIClient.generate(self, system_prompt: str, user_prompt: str) -> str`
  - `AIClient.embed_query(self, text: str) -> list[float]`
  - **Contract with Task 9:** when `system_prompt` contains the literal substring `Return ONLY JSON`, `FakeAIClient.generate` returns valid JSON: `{"claims": [{"text": "fake claim", "verdict": "supported"}]}`. Otherwise it returns a deterministic string starting with `[fake:<8-hex>]`.

- [ ] **Step 1: Write the failing tests** — append to `backend/tests/test_fake_ai.py`:

```python
import json


def test_generate_is_deterministic():
    fake = FakeAIClient()
    a = fake.generate("system", "user prompt")
    b = fake.generate("system", "user prompt")
    assert a == b
    assert a.startswith("[fake:")


def test_generate_varies_with_prompt():
    fake = FakeAIClient()
    assert fake.generate("system", "one") != fake.generate("system", "two")


def test_generate_returns_json_for_judge_prompts():
    fake = FakeAIClient()
    out = fake.generate("You are a judge. Return ONLY JSON.", "answer and context")
    parsed = json.loads(out)
    assert parsed["claims"][0]["verdict"] in ("supported", "unsupported")


def test_embed_query_matches_passage_embedding():
    fake = FakeAIClient()
    assert fake.embed_query("supply and demand") == fake.embed(["supply and demand"])[0]
```

(Keep the file's existing imports; `FakeAIClient` is already imported there.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_fake_ai.py -v`
Expected: 4 new tests FAIL with `AttributeError: 'FakeAIClient' object has no attribute 'generate'` (and `embed_query`).

- [ ] **Step 3: Implement.** In `ai/base.py`, add two methods to the `AIClient` Protocol (after `embed`):

```python
    def embed_query(self, text: str) -> list[float]:
        """Return the embedding for a retrieval query.

        Asymmetric-embedding models (nv-embedqa) encode queries and passages
        differently; symmetric fakes may return the same vector as `embed`.
        """
        ...

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        """Return the LLM completion for a system+user prompt pair."""
        ...
```

In `ai/fake.py`, add to `FakeAIClient`:

```python
    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        # Judge prompts (see pipeline/judge.py) need parseable JSON to keep the
        # eval harness runnable offline; everything else gets a deterministic
        # tag so tests can assert both stability and prompt-sensitivity.
        if "Return ONLY JSON" in system_prompt:
            return '{"claims": [{"text": "fake claim", "verdict": "supported"}]}'
        digest = hashlib.md5(f"{system_prompt}\n\n{user_prompt}".encode()).hexdigest()[:8]
        return f"[fake:{digest}] {user_prompt[:160]}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_fake_ai.py -v` → all PASS. Also `uv run ruff check src tests`.

- [ ] **Step 5: Commit (orchestrator)**

```bash
git add backend/src/koherent/ai/base.py backend/src/koherent/ai/fake.py backend/tests/test_fake_ai.py
git commit -m "feat(ai): add generate() and embed_query() to the AIClient seam"
```

---

### Task 2: Text chunker for documents

**Files:**
- Create: `backend/src/koherent/pipeline/text_chunking.py`
- Test: `backend/tests/test_text_chunking.py`

**Interfaces:**
- Produces: `TextChunk(index: int, content: str)` (frozen dataclass) and
  `chunk_text(text: str, target_words: int = 250, overlap_words: int = 50) -> list[TextChunk]`.

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_text_chunking.py`:

```python
import pytest

from koherent.pipeline.text_chunking import TextChunk, chunk_text


def test_empty_text_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_short_text_is_one_chunk():
    chunks = chunk_text("Supply and demand set prices.")
    assert chunks == [TextChunk(index=0, content="Supply and demand set prices.")]


def test_short_paragraphs_merge_into_one_chunk():
    text = "First paragraph here.\n\nSecond paragraph here."
    chunks = chunk_text(text, target_words=50, overlap_words=10)
    assert len(chunks) == 1
    assert "First paragraph" in chunks[0].content
    assert "Second paragraph" in chunks[0].content


def test_paragraph_boundary_starts_new_chunk_when_target_exceeded():
    para_a = " ".join(f"a{i}" for i in range(40))
    para_b = " ".join(f"b{i}" for i in range(40))
    chunks = chunk_text(f"{para_a}\n\n{para_b}", target_words=50, overlap_words=10)
    assert len(chunks) == 2
    assert chunks[0].content == para_a
    assert chunks[1].content == para_b


def test_long_paragraph_splits_with_overlap():
    words = [f"w{i}" for i in range(120)]
    chunks = chunk_text(" ".join(words), target_words=50, overlap_words=10)
    assert len(chunks) == 3
    first_words = chunks[0].content.split()
    second_words = chunks[1].content.split()
    assert first_words[-10:] == second_words[:10]  # overlap carried over
    assert [c.index for c in chunks] == [0, 1, 2]


def test_overlap_must_be_smaller_than_target():
    with pytest.raises(ValueError):
        chunk_text("some text", target_words=10, overlap_words=10)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_text_chunking.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'koherent.pipeline.text_chunking'`.

- [ ] **Step 3: Implement** — `backend/src/koherent/pipeline/text_chunking.py`:

```python
"""Chunk document text into embedding-sized pieces.

Separate from pipeline/chunking.py, which buckets ASR words by *time*;
documents have no timeline, so we window by word count instead. Paragraph
boundaries are respected where possible: short paragraphs merge into one
chunk, and a paragraph longer than the target is split into word windows
that carry `overlap_words` words forward so no idea is cut mid-context.
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    index: int
    content: str


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def chunk_text(
    text: str, target_words: int = 250, overlap_words: int = 50
) -> list[TextChunk]:
    if overlap_words >= target_words:
        raise ValueError("overlap_words must be smaller than target_words")

    # Greedily pack whole paragraphs up to the target...
    groups: list[list[str]] = []
    current: list[str] = []
    for para in _paragraphs(text):
        para_words = para.split()
        if current and len(current) + len(para_words) > target_words:
            groups.append(current)
            current = []
        current.extend(para_words)
    if current:
        groups.append(current)

    # ...then split any group that alone exceeds the target, with overlap.
    chunks: list[TextChunk] = []
    for group in groups:
        start = 0
        while start < len(group):
            window = group[start : start + target_words]
            chunks.append(TextChunk(index=len(chunks), content=" ".join(window)))
            if start + target_words >= len(group):
                break
            start += target_words - overlap_words
    return chunks
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_text_chunking.py -v` → all PASS. `uv run ruff check src tests`.

- [ ] **Step 5: Commit (orchestrator)**

```bash
git add backend/src/koherent/pipeline/text_chunking.py backend/tests/test_text_chunking.py
git commit -m "feat(pipeline): paragraph-aware text chunker for document ingestion"
```

---

### Task 3: Document text extraction (.txt/.md/.pdf)

**Files:**
- Create: `backend/src/koherent/pipeline/extraction.py`
- Modify: `backend/pyproject.toml` (add `"pypdf>=5"` to `[project] dependencies`)
- Test: `backend/tests/test_extraction.py`

**Interfaces:**
- Produces:
  - `extract_text(data: bytes, filename: str) -> str`
  - `UnsupportedDocumentError(ValueError)` — route layer maps to HTTP 415
  - `EmptyDocumentError(ValueError)` — route layer maps to HTTP 422

- [ ] **Step 1: Add the dependency**

In `backend/pyproject.toml` `[project] dependencies`, add `"pypdf>=5",` after `"openai>=1.0",`. Run: `uv sync --extra dev`. Expected: pypdf installs.

- [ ] **Step 2: Write the failing tests** — `backend/tests/test_extraction.py`:

```python
import pytest

from koherent.pipeline.extraction import (
    EmptyDocumentError,
    UnsupportedDocumentError,
    extract_text,
)


def test_txt_roundtrip():
    assert extract_text(b"hello notes", "notes.txt") == "hello notes"


def test_md_roundtrip():
    assert extract_text(b"# Week 1\n\nSupply and demand.", "week1.md").startswith("# Week 1")


def test_unsupported_suffix_raises():
    with pytest.raises(UnsupportedDocumentError):
        extract_text(b"...", "slides.docx")


def test_empty_document_raises():
    with pytest.raises(EmptyDocumentError):
        extract_text(b"   \n ", "empty.txt")


def test_pdf_pages_are_joined(monkeypatch):
    class FakePage:
        def __init__(self, text):
            self._text = text

        def extract_text(self):
            return self._text

    class FakeReader:
        def __init__(self, stream):
            self.pages = [FakePage("page one"), FakePage("page two")]

    monkeypatch.setattr("koherent.pipeline.extraction.PdfReader", FakeReader)
    assert extract_text(b"%PDF-fake", "doc.pdf") == "page one\n\npage two"


def test_blank_pdf_raises_empty(monkeypatch):
    class FakePage:
        def extract_text(self):
            return None

    class FakeReader:
        def __init__(self, stream):
            self.pages = [FakePage()]

    monkeypatch.setattr("koherent.pipeline.extraction.PdfReader", FakeReader)
    with pytest.raises(EmptyDocumentError):
        extract_text(b"%PDF-fake", "doc.pdf")
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_extraction.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'koherent.pipeline.extraction'`.

- [ ] **Step 4: Implement** — `backend/src/koherent/pipeline/extraction.py`:

```python
"""Extract plain text from uploaded course-material documents.

Dispatch is by filename suffix — browsers are unreliable about MIME types
for .md files, and the suffix is what users actually see. PDF extraction
uses pypdf; scanned/image-only PDFs yield no text and are rejected as
empty rather than silently ingested as blank chunks.
"""
import io
from pathlib import Path

from pypdf import PdfReader


class UnsupportedDocumentError(ValueError):
    """Document type we do not ingest (route layer maps this to HTTP 415)."""


class EmptyDocumentError(ValueError):
    """No extractable text (route layer maps this to HTTP 422)."""


_TEXT_SUFFIXES = {".txt", ".md"}


def extract_text(data: bytes, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        text = data.decode("utf-8", errors="replace")
    elif suffix == ".pdf":
        reader = PdfReader(io.BytesIO(data))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
    else:
        raise UnsupportedDocumentError(f"Unsupported document type: {suffix or '(none)'}")
    if not text.strip():
        raise EmptyDocumentError("Document contains no extractable text")
    return text.strip()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_extraction.py -v` → all PASS. `uv run ruff check src tests`.

- [ ] **Step 6: Commit (orchestrator)**

```bash
git add backend/src/koherent/pipeline/extraction.py backend/tests/test_extraction.py backend/pyproject.toml backend/uv.lock
git commit -m "feat(pipeline): extract text from txt/md/pdf uploads"
```

---

### Task 4: Top-k retrieval + query-typed embeddings

**Files:**
- Create: `backend/src/koherent/pipeline/retrieval.py`
- Modify: `backend/src/koherent/ai/embeddings.py`
- Test: `backend/tests/test_retrieval.py`, `backend/tests/test_embeddings.py` (append)

**Interfaces:**
- Consumes: `cosine` from `koherent.pipeline.alignment`.
- Produces:
  - `Candidate(source: str, ref_id: uuid.UUID, label: str, content: str, vector: list[float])` (frozen dataclass; `source` is `"material"` or `"transcript"`)
  - `ScoredChunk(source: str, ref_id: uuid.UUID, label: str, content: str, score: float)` (frozen dataclass)
  - `top_k(query_vector: list[float], candidates: list[Candidate], k: int = 5) -> list[ScoredChunk]`
  - `NIMEmbedder.embed(self, texts: list[str], *, input_type: str | None = None)` — per-call override of the constructor default; also new optional `client=None` constructor param for offline tests.

- [ ] **Step 1: Write the failing retrieval tests** — `backend/tests/test_retrieval.py`:

```python
import uuid

from koherent.pipeline.retrieval import Candidate, ScoredChunk, top_k


def _cand(content: str, vector: list[float], source: str = "material") -> Candidate:
    return Candidate(
        source=source, ref_id=uuid.uuid4(), label="econ_notes.md", content=content, vector=vector
    )


def test_orders_by_descending_cosine():
    query = [1.0, 0.0]
    close = _cand("close", [2.0, 0.1])
    far = _cand("far", [0.1, 2.0])
    results = top_k(query, [far, close], k=2)
    assert [r.content for r in results] == ["close", "far"]
    assert results[0].score > results[1].score


def test_k_larger_than_candidates_returns_all():
    results = top_k([1.0, 0.0], [_cand("only", [1.0, 0.0])], k=5)
    assert len(results) == 1
    assert isinstance(results[0], ScoredChunk)


def test_tie_keeps_original_candidate_order():
    a = _cand("first", [1.0, 0.0])
    b = _cand("second", [2.0, 0.0])  # same direction => same cosine
    results = top_k([1.0, 0.0], [a, b], k=2)
    assert [r.content for r in results] == ["first", "second"]


def test_empty_candidates_returns_empty():
    assert top_k([1.0, 0.0], [], k=5) == []


def test_carries_source_and_label_through():
    c = _cand("content", [1.0, 0.0], source="transcript")
    result = top_k([1.0, 0.0], [c], k=1)[0]
    assert result.source == "transcript"
    assert result.ref_id == c.ref_id
    assert result.label == c.label
```

- [ ] **Step 2: Write the failing embeddings tests** — append to `backend/tests/test_embeddings.py`:

```python
class _CapturingClient:
    """Stands in for the OpenAI SDK client; records the embeddings call."""

    def __init__(self):
        self.kwargs = None
        outer = self

        class _Embeddings:
            def create(self, **kwargs):
                outer.kwargs = kwargs

                class _Item:
                    embedding = [0.0]

                class _Response:
                    data = [_Item() for _ in kwargs["input"]]

                return _Response()

        self.embeddings = _Embeddings()


def test_embed_defaults_to_passage_input_type():
    fake_sdk = _CapturingClient()
    embedder = NIMEmbedder(api_key="test-key", client=fake_sdk)
    embedder.embed(["some text"])
    assert fake_sdk.kwargs["extra_body"]["input_type"] == "passage"


def test_embed_input_type_override():
    fake_sdk = _CapturingClient()
    embedder = NIMEmbedder(api_key="test-key", client=fake_sdk)
    embedder.embed(["a question"], input_type="query")
    assert fake_sdk.kwargs["extra_body"]["input_type"] == "query"
```

(Add `from koherent.ai.embeddings import NIMEmbedder` to that file's imports if not present.)

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_retrieval.py tests/test_embeddings.py -v`
Expected: retrieval tests FAIL with `ModuleNotFoundError`; embeddings tests FAIL with `TypeError: ... unexpected keyword argument 'client'`.

- [ ] **Step 4: Implement retrieval** — `backend/src/koherent/pipeline/retrieval.py`:

```python
"""Top-k retrieval over embedded chunks.

Pure and DB-free, like alignment.py: callers build Candidates from whatever
rows they queried (material chunks, transcript chunks) and get back the k
best matches by cosine similarity. Python-loop scan is deliberate — a class's
corpus is thousands of chunks at most (pgvector is the documented scale path,
wiki D-026).
"""
import uuid
from dataclasses import dataclass

from koherent.pipeline.alignment import cosine


@dataclass(frozen=True)
class Candidate:
    source: str  # "material" | "transcript"
    ref_id: uuid.UUID
    label: str
    content: str
    vector: list[float]


@dataclass(frozen=True)
class ScoredChunk:
    source: str
    ref_id: uuid.UUID
    label: str
    content: str
    score: float


def top_k(
    query_vector: list[float], candidates: list[Candidate], k: int = 5
) -> list[ScoredChunk]:
    scored = [
        ScoredChunk(
            source=c.source,
            ref_id=c.ref_id,
            label=c.label,
            content=c.content,
            score=cosine(query_vector, c.vector),
        )
        for c in candidates
    ]
    scored.sort(key=lambda s: -s.score)  # sort is stable: ties keep candidate order
    return scored[:k]
```

- [ ] **Step 5: Implement the embeddings change.** In `ai/embeddings.py`, change the constructor and `embed`:

```python
    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = _EMBED_MODEL,
        input_type: str = "passage",
        client=None,
    ) -> None:
        if client is None:
            key = api_key or settings.nvidia_api_key
            if not key:
                raise ValueError("NVIDIA API key is required (set NVIDIA_API_KEY).")
            client = OpenAI(base_url=_NIM_BASE_URL, api_key=key)
        self._client = client
        self._model = model
        self._input_type = input_type

    def embed(self, texts: list[str], *, input_type: str | None = None) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(
            model=self._model,
            input=texts,
            extra_body={"input_type": input_type or self._input_type, "truncate": "END"},
        )
        return _response_to_vectors(response)
```

Also update the module docstring's parenthetical: queries are now embedded as `"query"` via the per-call override (delete the "documented refinement" sentence).

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_retrieval.py tests/test_embeddings.py -v` → all PASS. `uv run ruff check src tests`.

- [ ] **Step 7: Commit (orchestrator)**

```bash
git add backend/src/koherent/pipeline/retrieval.py backend/src/koherent/ai/embeddings.py backend/tests/test_retrieval.py backend/tests/test_embeddings.py
git commit -m "feat(pipeline): top-k retrieval; embed queries with query input_type"
```

---

### Task 5: Materials + summary data model, migration 0003

**Files:**
- Modify: `backend/src/koherent/models.py`
- Create: `backend/alembic/versions/0003_materials.py`
- Test: `backend/tests/test_material_models.py`

**Interfaces:**
- Produces ORM classes (exact names/columns later tasks rely on):
  - `Material`: `id`, `class_id` (FK classes CASCADE, indexed), `filename: str(255)`, `media_type: str(100)`, `size_bytes: BigInteger`, `extracted_chars: BigInteger`, `created_at`; relationship `chunks` (cascade all, delete-orphan); `Class.materials` back-populated relationship.
  - `MaterialChunk`: `id`, `material_id` (FK materials CASCADE, indexed), `chunk_index: BigInteger`, `content: Text`, `embedding: ARRAY(Float) NOT NULL`, `created_at`; relationship `material`.
  - `LectureSummary`: `id`, `lecture_id` (FK lectures CASCADE, unique, indexed), `content: Text`, `model: str(100)`, `created_at`; `Lecture.summary` back-populated one-to-one relationship.

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_material_models.py`:

```python
from koherent.models import (
    Class,
    Lecture,
    LectureSummary,
    Material,
    MaterialChunk,
)


def _make_class(db) -> Class:
    klass = Class(name="Econ 101", join_code="ABC123", owner_token="tok-" + "x" * 8)
    db.add(klass)
    db.commit()
    return klass


def test_material_with_chunks_persists(db):
    klass = _make_class(db)
    material = Material(
        class_id=klass.id,
        filename="econ_notes.md",
        media_type="text/markdown",
        size_bytes=1234,
        extracted_chars=1000,
    )
    material.chunks = [
        MaterialChunk(chunk_index=0, content="supply and demand", embedding=[0.1, 0.2]),
        MaterialChunk(chunk_index=1, content="elasticity", embedding=[0.3, 0.4]),
    ]
    db.add(material)
    db.commit()
    db.refresh(material)
    assert len(material.chunks) == 2
    assert material.chunks[0].embedding == [0.1, 0.2]


def test_deleting_class_cascades_to_materials_and_chunks(db):
    klass = _make_class(db)
    material = Material(
        class_id=klass.id,
        filename="a.txt",
        media_type="text/plain",
        size_bytes=1,
        extracted_chars=1,
    )
    material.chunks = [MaterialChunk(chunk_index=0, content="x", embedding=[1.0])]
    db.add(material)
    db.commit()
    db.delete(klass)
    db.commit()
    assert db.query(Material).count() == 0
    assert db.query(MaterialChunk).count() == 0


def test_lecture_summary_one_to_one(db):
    klass = _make_class(db)
    lecture = Lecture(class_id=klass.id)
    db.add(lecture)
    db.commit()
    summary = LectureSummary(lecture_id=lecture.id, content="## Overview", model="fake")
    db.add(summary)
    db.commit()
    db.refresh(lecture)
    assert lecture.summary is not None
    assert lecture.summary.content == "## Overview"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `TEST_DATABASE_URL=... uv run pytest tests/test_material_models.py -v`
Expected: FAIL with `ImportError: cannot import name 'Material'`.

- [ ] **Step 3: Implement models.** Append to `models.py` (following the existing style exactly). Add to `Class`:

```python
    materials: Mapped[list["Material"]] = relationship(
        back_populates="class_", cascade="all, delete-orphan"
    )
```

Add to `Lecture`:

```python
    summary: Mapped["LectureSummary | None"] = relationship(
        back_populates="lecture", cascade="all, delete-orphan", uselist=False
    )
```

New classes at the end of the file:

```python
class Material(Base):
    __tablename__ = "materials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    extracted_chars: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    class_: Mapped[Class] = relationship(back_populates="materials")
    chunks: Mapped[list["MaterialChunk"]] = relationship(
        back_populates="material", cascade="all, delete-orphan"
    )


class MaterialChunk(Base):
    __tablename__ = "material_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    material_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("materials.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    material: Mapped[Material] = relationship(back_populates="chunks")


class LectureSummary(Base):
    __tablename__ = "lecture_summaries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    lecture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lectures.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lecture: Mapped[Lecture] = relationship(back_populates="summary")
```

- [ ] **Step 4: Write the migration** — `backend/alembic/versions/0003_materials.py` (mirror 0002's style):

```python
"""materials, material chunks, lecture summaries

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision = "0003"
down_revision = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "materials",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("class_id", sa.UUID(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("media_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("extracted_chars", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["class_id"], ["classes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_materials_class_id"), "materials", ["class_id"], unique=False)

    op.create_table(
        "material_chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("material_id", sa.UUID(), nullable=False),
        sa.Column("chunk_index", sa.BigInteger(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", sa.ARRAY(sa.Float()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_material_chunks_material_id"), "material_chunks", ["material_id"], unique=False
    )

    op.create_table(
        "lecture_summaries",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("lecture_id", sa.UUID(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["lecture_id"], ["lectures.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_lecture_summaries_lecture_id"), "lecture_summaries", ["lecture_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_lecture_summaries_lecture_id"), table_name="lecture_summaries")
    op.drop_table("lecture_summaries")
    op.drop_index(op.f("ix_material_chunks_material_id"), table_name="material_chunks")
    op.drop_table("material_chunks")
    op.drop_index(op.f("ix_materials_class_id"), table_name="materials")
    op.drop_table("materials")
```

- [ ] **Step 5: Run tests + migration**

Run: `TEST_DATABASE_URL=... uv run pytest tests/test_material_models.py -v` → PASS (conftest creates tables from metadata).
Run: `uv run alembic upgrade head` (against the dev DB). Expected: `Running upgrade 0002 -> 0003`.
`uv run ruff check src tests`.

- [ ] **Step 6: Commit (orchestrator)**

```bash
git add backend/src/koherent/models.py backend/alembic/versions/0003_materials.py backend/tests/test_material_models.py
git commit -m "feat(models): materials, material chunks, lecture summaries (migration 0003)"
```

---

### Task 6: Authz hardening — shared access helpers, scoped report

**Files:**
- Create: `backend/src/koherent/routes/access.py`
- Modify: `backend/src/koherent/routes/processing.py`, `backend/src/koherent/routes/lectures.py`
- Test: `backend/tests/test_processing.py` (append), `backend/tests/test_report.py` (modify + append)

**Interfaces:**
- Produces (Wave-3 route tasks import these):
  - `load_lecture_for_student(lecture_id: uuid.UUID, student: Student, db: Session) -> Lecture` — 404 if missing, 403 if other class.
  - `require_class_member(class_id: uuid.UUID, student: Student) -> None` — 403 if `class_id != student.class_id`.
- Behavior change: `GET /lectures/{id}/report` now returns **only the calling student's notes**.

- [ ] **Step 1: Write the failing tests.** Append to `backend/tests/test_processing.py`:

```python
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
```

Append to `backend/tests/test_report.py` (reuse that file's existing seed helpers; if it has none, copy `_join`/`_seed_lecture_with_notes_and_audio` from `test_processing.py`):

```python
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
```

> If existing tests in `test_report.py` assert that a report contains notes from multiple students, update them to the new scoped behavior (each caller sees only their own notes) — that scoping is the point of this task.

- [ ] **Step 2: Run tests to verify they fail**

Run: `TEST_DATABASE_URL=... uv run pytest tests/test_processing.py tests/test_report.py -v`
Expected: new tests FAIL (200 instead of 403; report contains both notes).

- [ ] **Step 3: Implement.** Create `backend/src/koherent/routes/access.py`:

```python
"""Shared authorization helpers for lecture- and class-scoped routes.

Membership rules live in one place so every router enforces the same
policy: 404 for resources that don't exist, 403 for resources that exist
but belong to another class (a student's view of "not yours").
"""
import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from koherent.models import Lecture, Student


def load_lecture_for_student(lecture_id: uuid.UUID, student: Student, db: Session) -> Lecture:
    lecture = db.get(Lecture, lecture_id)
    if lecture is None:
        raise HTTPException(status_code=404, detail="Lecture not found")
    if lecture.class_id != student.class_id:
        raise HTTPException(status_code=403, detail="Not a member of this lecture's class")
    return lecture


def require_class_member(class_id: uuid.UUID, student: Student) -> None:
    if class_id != student.class_id:
        raise HTTPException(status_code=403, detail="Not a member of this class")
```

In `routes/lectures.py`: delete the private `_load_lecture_for_student` and replace its uses with `load_lecture_for_student` imported from `koherent.routes.access` (same signature, same behavior — pure move).

In `routes/processing.py`:
- Import: `from koherent.routes.access import load_lecture_for_student`.
- In `process(...)`: before calling `process_lecture`, add `load_lecture_for_student(lecture_id, current, db)` (keep the existing `LookupError`/`NoAudioError` handling).
- In `report(...)`: replace the `db.get(Lecture, ...)` existence check with `load_lecture_for_student(lecture_id, current, db)`, and scope the notes query:

```python
    notes = list(
        db.scalars(
            select(Note).where(Note.lecture_id == lecture_id, Note.student_id == current.id)
        )
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `TEST_DATABASE_URL=... uv run pytest tests/test_processing.py tests/test_report.py tests/test_lectures.py tests/test_notes.py tests/test_audio.py -v` → all PASS. `uv run ruff check src tests`.

- [ ] **Step 5: Commit (orchestrator)**

```bash
git add backend/src/koherent/routes/access.py backend/src/koherent/routes/processing.py backend/src/koherent/routes/lectures.py backend/tests/test_processing.py backend/tests/test_report.py
git commit -m "fix(authz): enforce class membership on process/report; scope report to caller"
```

---

### Task 7: NIM chat adapter + RealAIClient composition + config

**Files:**
- Create: `backend/src/koherent/ai/chat.py`
- Modify: `backend/src/koherent/ai/real.py`, `backend/src/koherent/config.py`
- Test: `backend/tests/test_chat.py`

**Interfaces:**
- Consumes: `AIClient.generate` / `embed_query` shapes from Task 1; `NIMEmbedder.embed(..., input_type=...)` from Task 4.
- Produces:
  - Settings: `nim_chat_model: str = "meta/llama-3.3-70b-instruct"`, `context_char_budget: int = 12000`.
  - `NIMChatClient(api_key=None, model=None, temperature=0.2, client=None)` with `generate(system_prompt, user_prompt) -> str`.
  - `RealAIClient` gains `chat=None` constructor param, `generate(...)` delegation, and `embed_query(text) -> list[float]` (delegates to `self._embedder.embed([text], input_type="query")[0]`).

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_chat.py`:

```python
from koherent.ai.chat import NIMChatClient, _response_to_text
from koherent.ai.real import RealAIClient


class _Msg:
    content = "generated answer"


class _Choice:
    message = _Msg()


class _Response:
    choices = [_Choice()]


class _CapturingChatSDK:
    def __init__(self):
        self.kwargs = None
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.kwargs = kwargs
                return _Response()

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


def test_response_to_text_reads_first_choice():
    assert _response_to_text(_Response()) == "generated answer"


def test_generate_sends_system_and_user_messages():
    sdk = _CapturingChatSDK()
    chat = NIMChatClient(api_key="test-key", model="test/model", client=sdk)
    out = chat.generate("be helpful", "what is elasticity?")
    assert out == "generated answer"
    assert sdk.kwargs["model"] == "test/model"
    assert sdk.kwargs["messages"] == [
        {"role": "system", "content": "be helpful"},
        {"role": "user", "content": "what is elasticity?"},
    ]
    assert sdk.kwargs["temperature"] == 0.2


class _StubEmbedder:
    def __init__(self):
        self.calls = []

    def embed(self, texts, *, input_type=None):
        self.calls.append((texts, input_type))
        return [[1.0, 2.0] for _ in texts]


class _StubChat:
    def generate(self, system_prompt, user_prompt):
        return f"chat:{user_prompt}"


def test_real_client_delegates_generate_and_embed_query():
    embedder = _StubEmbedder()
    real = RealAIClient(transcriber=object(), embedder=embedder, chat=_StubChat())
    assert real.generate("sys", "hi") == "chat:hi"
    assert real.embed_query("a question") == [1.0, 2.0]
    assert embedder.calls == [(["a question"], "query")]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_chat.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'koherent.ai.chat'`.

- [ ] **Step 3: Implement config.** In `config.py`, after `anomaly_threshold`, add:

```python
    nim_chat_model: str = "meta/llama-3.3-70b-instruct"
    # Character cap on assembled retrieval context before an LLM call; keeps
    # prompts well inside the model window without token-counting machinery.
    context_char_budget: int = 12000
```

- [ ] **Step 4: Implement the adapter** — `backend/src/koherent/ai/chat.py`:

```python
"""LLM text generation via NVIDIA NIM chat completions, behind the AIClient seam.

Same transport story as embeddings.py: NIM exposes an OpenAI-compatible
endpoint, so the OpenAI SDK is pointed at NVIDIA's base URL and one
NVIDIA_API_KEY covers ASR, embeddings, and generation. All NVIDIA chat
specifics are contained here.
"""
from openai import OpenAI

from koherent.config import settings

_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"


def _response_to_text(response) -> str:
    """Pure mapping from an OpenAI-style chat response to the completion text."""
    return response.choices[0].message.content or ""


class NIMChatClient:
    """Generation adapter: (system prompt, user prompt) -> completion text."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        client=None,
    ) -> None:
        if client is None:
            key = api_key or settings.nvidia_api_key
            if not key:
                raise ValueError("NVIDIA API key is required (set NVIDIA_API_KEY).")
            client = OpenAI(base_url=_NIM_BASE_URL, api_key=key)
        self._client = client
        self._model = model or settings.nim_chat_model
        self._temperature = temperature

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self._temperature,
        )
        return _response_to_text(response)
```

- [ ] **Step 5: Compose into RealAIClient.** Update `ai/real.py`:

```python
"""The real AIClient: NVIDIA Riva ASR + NIM embeddings + NIM chat.

Composes three adapters behind the single seam. Constructed only for real
runs (all adapters require an NVIDIA API key); tests override the DI
provider with FakeAIClient, so this is never built during the offline suite.
"""

from koherent.ai.base import Transcription
from koherent.ai.chat import NIMChatClient
from koherent.ai.embeddings import NIMEmbedder
from koherent.ai.riva import RivaClient


class RealAIClient:
    def __init__(self, transcriber=None, embedder=None, chat=None) -> None:
        self._transcriber = transcriber or RivaClient()
        self._embedder = embedder or NIMEmbedder()
        self._chat = chat or NIMChatClient()

    def transcribe(self, audio_path: str) -> Transcription:
        return self._transcriber.transcribe(audio_path)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._embedder.embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embedder.embed([text], input_type="query")[0]

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        return self._chat.generate(system_prompt, user_prompt)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_chat.py -v` → all PASS. `uv run ruff check src tests`.

- [ ] **Step 7: Commit (orchestrator)**

```bash
git add backend/src/koherent/ai/chat.py backend/src/koherent/ai/real.py backend/src/koherent/config.py backend/tests/test_chat.py
git commit -m "feat(ai): NIM chat adapter; RealAIClient generate/embed_query"
```

---

### Task 8: Prompt builders

**Files:**
- Create: `backend/src/koherent/pipeline/prompts.py`
- Test: `backend/tests/test_prompts.py`

**Interfaces:**
- Consumes: `ScoredChunk` from `koherent.pipeline.retrieval` (Task 4).
- Produces (route tasks and evals import these exact names):
  - `GROUNDED_SYSTEM_PROMPT: str`, `SUMMARY_SYSTEM_PROMPT: str`, `REVIEW_SYSTEM_PROMPT: str`
  - `build_context_block(chunks: list[ScoredChunk], char_budget: int = 12000) -> tuple[str, bool]` — returns `(numbered block, truncated_flag)`
  - `build_ask_prompt(question: str, context_block: str) -> str`
  - `build_explain_prompt(concept: str, context_block: str) -> str`
  - `build_summary_prompt(lecture_title: str | None, chunk_texts: list[str]) -> str`
  - `ReviewItem(note_content: str, matched_content: str | None, similarity: float | None)` (frozen dataclass)
  - `build_review_prompt(items: list[ReviewItem]) -> str`

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_prompts.py`:

```python
import uuid

from koherent.pipeline.prompts import (
    GROUNDED_SYSTEM_PROMPT,
    ReviewItem,
    build_ask_prompt,
    build_context_block,
    build_explain_prompt,
    build_review_prompt,
    build_summary_prompt,
)
from koherent.pipeline.retrieval import ScoredChunk


def _chunk(content: str, label: str = "econ_notes.md") -> ScoredChunk:
    return ScoredChunk(
        source="material", ref_id=uuid.uuid4(), label=label, content=content, score=0.9
    )


def test_context_block_numbers_and_labels_chunks():
    block, truncated = build_context_block([_chunk("alpha"), _chunk("beta", label="lecture:L1")])
    assert "[1] (econ_notes.md) alpha" in block
    assert "[2] (lecture:L1) beta" in block
    assert truncated is False


def test_context_block_respects_char_budget():
    block, truncated = build_context_block([_chunk("x" * 100), _chunk("y" * 100)], char_budget=120)
    assert truncated is True
    assert "y" not in block  # second chunk dropped, first kept whole


def test_ask_prompt_contains_question_and_context():
    prompt = build_ask_prompt("What is elasticity?", "[1] (m) context here")
    assert "What is elasticity?" in prompt
    assert "[1] (m) context here" in prompt


def test_explain_prompt_asks_for_definition_intuition_example():
    prompt = build_explain_prompt("elasticity", "[1] (m) ctx")
    for part in ("definition", "intuition", "example"):
        assert part in prompt.lower()


def test_summary_prompt_includes_title_and_chunks_in_order():
    prompt = build_summary_prompt("Supply & Demand", ["first chunk", "second chunk"])
    assert "Supply & Demand" in prompt
    assert prompt.index("first chunk") < prompt.index("second chunk")


def test_review_prompt_lists_notes_with_matches():
    items = [
        ReviewItem(note_content="wrong note", matched_content="what was said", similarity=0.3),
        ReviewItem(note_content="orphan note", matched_content=None, similarity=None),
    ]
    prompt = build_review_prompt(items)
    assert "wrong note" in prompt
    assert "what was said" in prompt
    assert "orphan note" in prompt


def test_grounded_system_prompt_demands_citations():
    assert "context" in GROUNDED_SYSTEM_PROMPT.lower()
    assert "cite" in GROUNDED_SYSTEM_PROMPT.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_prompts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'koherent.pipeline.prompts'`.

- [ ] **Step 3: Implement** — `backend/src/koherent/pipeline/prompts.py`:

```python
"""Prompt construction for the assistant endpoints.

Pure string builders, kept out of route handlers so grounding rules are
testable and consistent: every generative endpoint speaks to the model
through these templates, and every answer is grounded in a numbered
context block whose entries the model must cite.
"""
from dataclasses import dataclass

from koherent.pipeline.retrieval import ScoredChunk

GROUNDED_SYSTEM_PROMPT = (
    "You are a study assistant for a university class. Answer ONLY from the "
    "numbered context excerpts provided by the user. If the context does not "
    'contain the answer, reply exactly: "Not covered in the course materials." '
    "Cite the excerpt numbers you used in square brackets, e.g. [1][3]. "
    "Be concise and factual; never invent material that is not in the context."
)

SUMMARY_SYSTEM_PROMPT = (
    "You are a study assistant. Produce a structured markdown summary of a "
    "lecture transcript with exactly these sections: '## Overview' (2-3 "
    "sentences), '## Key concepts' (bulleted term: one-line definition), and "
    "'## Section by section' (one bullet per transcript section, in order). "
    "Use only what the transcript says; do not add outside knowledge."
)

REVIEW_SYSTEM_PROMPT = (
    "You are a tutor writing personalized review prompts for one student. "
    "For each weak spot you are given (their note, and what the lecture "
    "actually said), write: what the lecture actually said (1-2 sentences), "
    "then 1-2 short check-yourself questions targeting the gap. Ground every "
    "item in the provided lecture excerpts only. Format as markdown with one "
    "'### Review N' section per weak spot."
)


def build_context_block(
    chunks: list[ScoredChunk], char_budget: int = 12000
) -> tuple[str, bool]:
    """Number chunks into a citable block, dropping whole chunks past the budget."""
    entries: list[str] = []
    used = 0
    truncated = False
    for i, chunk in enumerate(chunks, start=1):
        entry = f"[{i}] ({chunk.label}) {chunk.content}"
        if used + len(entry) > char_budget:
            truncated = True
            break
        entries.append(entry)
        used += len(entry)
    return "\n\n".join(entries), truncated


def build_ask_prompt(question: str, context_block: str) -> str:
    return f"Context excerpts:\n\n{context_block}\n\nQuestion: {question}"


def build_explain_prompt(concept: str, context_block: str) -> str:
    return (
        f"Context excerpts:\n\n{context_block}\n\n"
        f'Explain the concept "{concept}" using only the context above. '
        "Structure the explanation as: definition, intuition, example."
    )


def build_summary_prompt(lecture_title: str | None, chunk_texts: list[str]) -> str:
    title = lecture_title or "(untitled lecture)"
    sections = "\n\n".join(
        f"Section {i + 1}:\n{text}" for i, text in enumerate(chunk_texts)
    )
    return f"Lecture title: {title}\n\nTranscript sections, in order:\n\n{sections}"


@dataclass(frozen=True)
class ReviewItem:
    note_content: str
    matched_content: str | None
    similarity: float | None


def build_review_prompt(items: list[ReviewItem]) -> str:
    blocks: list[str] = []
    for i, item in enumerate(items, start=1):
        matched = item.matched_content or "(no matching lecture content was found)"
        similarity = f"{item.similarity:.2f}" if item.similarity is not None else "none"
        blocks.append(
            f"Weak spot {i} (match similarity: {similarity}):\n"
            f"Student's note: {item.note_content}\n"
            f"What the lecture said: {matched}"
        )
    return "The student's weak spots, from their own lecture notes:\n\n" + "\n\n".join(blocks)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_prompts.py -v` → all PASS. `uv run ruff check src tests`.

- [ ] **Step 5: Commit (orchestrator)**

```bash
git add backend/src/koherent/pipeline/prompts.py backend/tests/test_prompts.py
git commit -m "feat(pipeline): grounded prompt builders for ask/explain/summary/review"
```

---

### Task 9: LLM-judge prompt + parser

**Files:**
- Create: `backend/src/koherent/pipeline/judge.py`
- Test: `backend/tests/test_judge.py`

**Interfaces:**
- Consumes: **Contract with Task 1** — `JUDGE_SYSTEM_PROMPT` MUST contain the literal substring `Return ONLY JSON` (FakeAIClient keys on it).
- Produces (eval harness imports these):
  - `JUDGE_SYSTEM_PROMPT: str`
  - `build_judge_user_prompt(answer: str, context_block: str) -> str`
  - `ClaimVerdict(text: str, supported: bool)` (frozen dataclass)
  - `JudgeResult(claims: list[ClaimVerdict], parse_error: bool)` (frozen dataclass)
  - `parse_judge_output(raw: str) -> JudgeResult`
  - `unsupported_rate(results: list[JudgeResult]) -> float | None` — fraction of claims unsupported across parseable results; `None` if there are no parseable claims.

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_judge.py`:

```python
from koherent.pipeline.judge import (
    JUDGE_SYSTEM_PROMPT,
    JudgeResult,
    build_judge_user_prompt,
    parse_judge_output,
    unsupported_rate,
)


def test_system_prompt_contains_fake_client_json_marker():
    assert "Return ONLY JSON" in JUDGE_SYSTEM_PROMPT


def test_user_prompt_contains_answer_and_context():
    prompt = build_judge_user_prompt("the answer", "[1] ctx")
    assert "the answer" in prompt
    assert "[1] ctx" in prompt


def test_parses_valid_judge_json():
    raw = '{"claims": [{"text": "a", "verdict": "supported"}, {"text": "b", "verdict": "unsupported"}]}'
    result = parse_judge_output(raw)
    assert result.parse_error is False
    assert [c.supported for c in result.claims] == [True, False]


def test_parses_json_wrapped_in_code_fence():
    raw = '```json\n{"claims": [{"text": "a", "verdict": "supported"}]}\n```'
    result = parse_judge_output(raw)
    assert result.parse_error is False
    assert len(result.claims) == 1


def test_malformed_output_sets_parse_error():
    result = parse_judge_output("I think the answer is mostly fine.")
    assert result.parse_error is True
    assert result.claims == []


def test_unknown_verdict_sets_parse_error():
    result = parse_judge_output('{"claims": [{"text": "a", "verdict": "maybe"}]}')
    assert result.parse_error is True


def test_unsupported_rate_across_results():
    results = [
        parse_judge_output('{"claims": [{"text": "a", "verdict": "supported"}]}'),
        parse_judge_output(
            '{"claims": [{"text": "b", "verdict": "unsupported"},'
            ' {"text": "c", "verdict": "supported"}]}'
        ),
        parse_judge_output("garbage"),  # excluded from the denominator
    ]
    assert unsupported_rate(results) == 1 / 3


def test_unsupported_rate_with_no_parseable_claims_is_none():
    assert unsupported_rate([parse_judge_output("garbage")]) is None
    assert unsupported_rate([]) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_judge.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'koherent.pipeline.judge'`.

- [ ] **Step 3: Implement** — `backend/src/koherent/pipeline/judge.py`:

```python
"""LLM-as-judge for groundedness: is each claim in an answer supported by context?

The judge is asked for strict JSON; parsing is tolerant of markdown code
fences (models add them) but strict about shape and verdict vocabulary —
anything else is a parse_error, counted separately rather than guessed at.
The phrase "Return ONLY JSON" is load-bearing: FakeAIClient detects it to
return parseable JSON, keeping the eval harness runnable offline.
"""
import json
import re
from dataclasses import dataclass, field

JUDGE_SYSTEM_PROMPT = (
    "You are a strict grading assistant. The user gives you an ANSWER and the "
    "CONTEXT excerpts it was generated from. Split the answer into its factual "
    "claims and judge each claim strictly against the context alone: a claim "
    'is "supported" only if the context states it. Return ONLY JSON matching '
    'this schema, with no other text: {"claims": [{"text": "<claim>", '
    '"verdict": "supported" | "unsupported"}]}'
)


def build_judge_user_prompt(answer: str, context_block: str) -> str:
    return f"ANSWER:\n{answer}\n\nCONTEXT:\n{context_block}"


@dataclass(frozen=True)
class ClaimVerdict:
    text: str
    supported: bool


@dataclass(frozen=True)
class JudgeResult:
    claims: list[ClaimVerdict] = field(default_factory=list)
    parse_error: bool = False


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$")


def parse_judge_output(raw: str) -> JudgeResult:
    cleaned = _FENCE_RE.sub("", raw.strip())
    try:
        payload = json.loads(cleaned)
        claims = []
        for item in payload["claims"]:
            verdict = item["verdict"]
            if verdict not in ("supported", "unsupported"):
                raise ValueError(f"unknown verdict: {verdict}")
            claims.append(ClaimVerdict(text=item["text"], supported=verdict == "supported"))
        return JudgeResult(claims=claims)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return JudgeResult(parse_error=True)


def unsupported_rate(results: list[JudgeResult]) -> float | None:
    claims = [c for r in results if not r.parse_error for c in r.claims]
    if not claims:
        return None
    return sum(1 for c in claims if not c.supported) / len(claims)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_judge.py -v` → all PASS. `uv run ruff check src tests`.

- [ ] **Step 5: Commit (orchestrator)**

```bash
git add backend/src/koherent/pipeline/judge.py backend/tests/test_judge.py
git commit -m "feat(pipeline): LLM-judge groundedness prompt and strict parser"
```

---

### Task 10: API scaffolding — schemas, skeleton routers, registration

**Files:**
- Modify: `backend/src/koherent/schemas.py`, `backend/src/koherent/main.py`
- Create: `backend/src/koherent/routes/materials.py`, `backend/src/koherent/routes/assistant.py`, `backend/src/koherent/routes/study.py` (skeletons — routers with no endpoints; bodies land in Wave 3)

**Interfaces:**
- Consumes: model shapes from Task 5.
- Produces (Wave-3 tasks fill in endpoints against these exact schemas):
  - `MaterialRead(id, class_id, filename, media_type, size_bytes, chunk_count: int, created_at)`
  - `MaterialList(items: list[MaterialRead])`
  - `Citation(source: str, chunk_id: uuid.UUID, label: str, content: str, score: float)`
  - `AskRequest(question: str)` (1–2000 chars), `ExplainRequest(concept: str)` (1–200 chars)
  - `GeneratedAnswer(answer: str, citations: list[Citation], truncated: bool, model: str)`
  - `LectureSummaryRead(lecture_id, content, model, created_at)`
  - `ReviewResponse(lecture_id: uuid.UUID, content: str, weak_note_count: int, model: str)`
  - Routers: `materials.router` (prefix `/classes`, tag `materials`), `assistant.router` (prefix `/classes`, tag `assistant`), `study.router` (prefix `/lectures`, tag `study`), all registered in `main.py`.

- [ ] **Step 1: Add schemas.** Append to `schemas.py`:

```python
class MaterialRead(BaseModel):
    id: uuid.UUID
    class_id: uuid.UUID
    filename: str
    media_type: str
    size_bytes: int
    chunk_count: int
    created_at: datetime


class MaterialList(BaseModel):
    items: list[MaterialRead]


class Citation(BaseModel):
    source: str
    chunk_id: uuid.UUID
    label: str
    content: str
    score: float


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class ExplainRequest(BaseModel):
    concept: str = Field(min_length=1, max_length=200)


class GeneratedAnswer(BaseModel):
    answer: str
    citations: list[Citation]
    truncated: bool
    model: str


class LectureSummaryRead(BaseModel):
    lecture_id: uuid.UUID
    content: str
    model: str
    created_at: datetime


class ReviewResponse(BaseModel):
    lecture_id: uuid.UUID
    content: str
    weak_note_count: int
    model: str
```

- [ ] **Step 2: Create skeleton routers.** `routes/materials.py`:

```python
"""Course-material ingestion routes. Endpoint bodies land with the materials task."""
from fastapi import APIRouter

router = APIRouter(prefix="/classes", tags=["materials"])
```

`routes/assistant.py`:

```python
"""Grounded Q&A routes (ask/explain). Endpoint bodies land with the assistant task."""
from fastapi import APIRouter

router = APIRouter(prefix="/classes", tags=["assistant"])
```

`routes/study.py`:

```python
"""Lecture study artifacts (summary/review). Endpoint bodies land with the study task."""
from fastapi import APIRouter

router = APIRouter(prefix="/lectures", tags=["study"])
```

- [ ] **Step 3: Register.** In `main.py`, extend the routes import and add three `include_router` lines:

```python
from koherent.routes import assistant, classes, lectures, materials, processing, study
```

```python
app.include_router(materials.router)
app.include_router(assistant.router)
app.include_router(study.router)
```

- [ ] **Step 4: Verify the app still boots**

Run: `TEST_DATABASE_URL=... uv run pytest tests/test_smoke.py tests/test_health.py -v` → PASS. `uv run ruff check src tests`.

- [ ] **Step 5: Commit (orchestrator)**

```bash
git add backend/src/koherent/schemas.py backend/src/koherent/main.py backend/src/koherent/routes/materials.py backend/src/koherent/routes/assistant.py backend/src/koherent/routes/study.py
git commit -m "feat(api): schemas and router scaffolding for materials/assistant/study"
```

---

### Task 11: Materials endpoints

**Files:**
- Modify: `backend/src/koherent/routes/materials.py`
- Test: `backend/tests/test_materials.py`

**Interfaces:**
- Consumes: `extract_text`/errors (Task 3), `chunk_text` (Task 2), `AIClient.embed` (existing), `Material`/`MaterialChunk` (Task 5), `require_class_member` (Task 6), schemas (Task 10).
- Produces: `POST /classes/{class_id}/materials` (multipart, 201 → `MaterialRead`), `GET /classes/{class_id}/materials` (200 → `MaterialList`).

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_materials.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `TEST_DATABASE_URL=... uv run pytest tests/test_materials.py -v`
Expected: FAIL with 405s (routes don't exist yet).

- [ ] **Step 3: Implement** — replace `routes/materials.py` body:

```python
"""Course-material ingestion: upload a document, extract, chunk, embed, store.

Processing is synchronous and inline (same decision as lecture processing,
wiki D-028): a class's documents are small and the corpus is bounded, so a
queue would be premature.
"""
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from koherent.ai.base import AIClient
from koherent.deps import get_ai_client, get_current_student, get_db
from koherent.models import Material, MaterialChunk, Student
from koherent.pipeline.extraction import (
    EmptyDocumentError,
    UnsupportedDocumentError,
    extract_text,
)
from koherent.pipeline.text_chunking import chunk_text
from koherent.routes.access import require_class_member
from koherent.schemas import MaterialList, MaterialRead

router = APIRouter(prefix="/classes", tags=["materials"])


def _to_read(material: Material) -> MaterialRead:
    return MaterialRead(
        id=material.id,
        class_id=material.class_id,
        filename=material.filename,
        media_type=material.media_type,
        size_bytes=material.size_bytes,
        chunk_count=len(material.chunks),
        created_at=material.created_at,
    )


@router.post(
    "/{class_id}/materials", response_model=MaterialRead, status_code=status.HTTP_201_CREATED
)
def upload_material(
    class_id: uuid.UUID,
    file: UploadFile = File(...),
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
    ai: AIClient = Depends(get_ai_client),
) -> MaterialRead:
    require_class_member(class_id, current)

    data = file.file.read()
    filename = file.filename or "upload"
    try:
        text = extract_text(data, filename)
    except UnsupportedDocumentError as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    except EmptyDocumentError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    chunks = chunk_text(text)
    vectors = ai.embed([c.content for c in chunks])

    material = Material(
        class_id=class_id,
        filename=filename,
        media_type=file.content_type or "application/octet-stream",
        size_bytes=len(data),
        extracted_chars=len(text),
    )
    material.chunks = [
        MaterialChunk(chunk_index=c.index, content=c.content, embedding=v)
        for c, v in zip(chunks, vectors)
    ]
    db.add(material)
    db.commit()
    db.refresh(material)
    return _to_read(material)


@router.get("/{class_id}/materials", response_model=MaterialList)
def list_materials(
    class_id: uuid.UUID,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
) -> MaterialList:
    require_class_member(class_id, current)
    materials = list(
        db.scalars(
            select(Material).where(Material.class_id == class_id).order_by(Material.created_at)
        )
    )
    return MaterialList(items=[_to_read(m) for m in materials])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `TEST_DATABASE_URL=... uv run pytest tests/test_materials.py -v` → all PASS. `uv run ruff check src tests`.

- [ ] **Step 5: Commit (orchestrator)**

```bash
git add backend/src/koherent/routes/materials.py backend/tests/test_materials.py
git commit -m "feat(api): course-material upload and listing with chunked embeddings"
```

---

### Task 12: Ask + Explain endpoints

**Files:**
- Modify: `backend/src/koherent/routes/assistant.py`
- Test: `backend/tests/test_assistant.py`

**Interfaces:**
- Consumes: `embed_query`/`generate` (Task 1/7), `Candidate`/`top_k` (Task 4), prompts (Task 8), `require_class_member` (Task 6), schemas (Task 10), models (Task 5 + existing).
- Produces: `POST /classes/{class_id}/ask` and `POST /classes/{class_id}/explain`, both 200 → `GeneratedAnswer`; 400 when the class has no indexed content; 502 on generation failure.

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_assistant.py`.

> Seed material chunks **directly in the DB** (not via the upload endpoint) — Task 11 builds that endpoint in the same wave, and these tests must not depend on it.

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `TEST_DATABASE_URL=... uv run pytest tests/test_assistant.py -v`
Expected: FAIL with 405s (routes don't exist yet).

- [ ] **Step 3: Implement** — replace `routes/assistant.py` body:

```python
"""Grounded Q&A over a class's corpus: uploaded materials + lecture transcripts.

The RAG loop: embed the query (as "query" — asymmetric model), rank every
chunk in the class by cosine, assemble the top k into a numbered context
block, and generate with a system prompt that forbids answering beyond it.
Citations returned to the caller are the same numbered chunks the model saw.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from koherent.ai.base import AIClient
from koherent.config import settings
from koherent.deps import get_ai_client, get_current_student, get_db
from koherent.models import Lecture, Material, MaterialChunk, Student, Transcript, TranscriptChunk
from koherent.pipeline.prompts import (
    GROUNDED_SYSTEM_PROMPT,
    build_ask_prompt,
    build_context_block,
    build_explain_prompt,
)
from koherent.pipeline.retrieval import Candidate, top_k
from koherent.routes.access import require_class_member
from koherent.schemas import AskRequest, Citation, ExplainRequest, GeneratedAnswer

router = APIRouter(prefix="/classes", tags=["assistant"])

_TOP_K = 5


def gather_candidates(class_id: uuid.UUID, db: Session) -> list[Candidate]:
    """Every embedded chunk in the class: material chunks and transcript chunks."""
    candidates: list[Candidate] = []
    material_rows = db.execute(
        select(MaterialChunk, Material.filename)
        .join(Material, MaterialChunk.material_id == Material.id)
        .where(Material.class_id == class_id)
    ).all()
    for chunk, filename in material_rows:
        candidates.append(
            Candidate(
                source="material",
                ref_id=chunk.id,
                label=filename,
                content=chunk.content,
                vector=chunk.embedding,
            )
        )
    transcript_rows = db.execute(
        select(TranscriptChunk, Lecture.title)
        .join(Transcript, TranscriptChunk.transcript_id == Transcript.id)
        .join(Lecture, Transcript.lecture_id == Lecture.id)
        .where(Lecture.class_id == class_id)
    ).all()
    for chunk, title in transcript_rows:
        candidates.append(
            Candidate(
                source="transcript",
                ref_id=chunk.id,
                label=f"lecture:{title or 'untitled'}",
                content=chunk.content,
                vector=chunk.embedding,
            )
        )
    return candidates


def _generate_grounded(
    class_id: uuid.UUID,
    query_text: str,
    build_user_prompt,
    db: Session,
    ai: AIClient,
) -> GeneratedAnswer:
    candidates = gather_candidates(class_id, db)
    if not candidates:
        raise HTTPException(
            status_code=400, detail="Class has no indexed content yet (upload materials or process a lecture)"
        )
    query_vector = ai.embed_query(query_text)
    ranked = top_k(query_vector, candidates, k=_TOP_K)
    context_block, truncated = build_context_block(ranked, settings.context_char_budget)
    try:
        answer = ai.generate(GROUNDED_SYSTEM_PROMPT, build_user_prompt(context_block))
    except Exception:
        raise HTTPException(status_code=502, detail="LLM generation failed")
    return GeneratedAnswer(
        answer=answer,
        citations=[
            Citation(
                source=r.source, chunk_id=r.ref_id, label=r.label, content=r.content, score=r.score
            )
            for r in ranked
        ],
        truncated=truncated,
        model=settings.nim_chat_model,
    )


@router.post("/{class_id}/ask", response_model=GeneratedAnswer)
def ask(
    class_id: uuid.UUID,
    payload: AskRequest,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
    ai: AIClient = Depends(get_ai_client),
) -> GeneratedAnswer:
    require_class_member(class_id, current)
    return _generate_grounded(
        class_id,
        payload.question,
        lambda block: build_ask_prompt(payload.question, block),
        db,
        ai,
    )


@router.post("/{class_id}/explain", response_model=GeneratedAnswer)
def explain(
    class_id: uuid.UUID,
    payload: ExplainRequest,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
    ai: AIClient = Depends(get_ai_client),
) -> GeneratedAnswer:
    require_class_member(class_id, current)
    return _generate_grounded(
        class_id,
        payload.concept,
        lambda block: build_explain_prompt(payload.concept, block),
        db,
        ai,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `TEST_DATABASE_URL=... uv run pytest tests/test_assistant.py -v` → all PASS. `uv run ruff check src tests`.

- [ ] **Step 5: Commit (orchestrator)**

```bash
git add backend/src/koherent/routes/assistant.py backend/tests/test_assistant.py
git commit -m "feat(api): grounded /ask and /explain over materials + transcripts"
```

---

### Task 13: Summary + Review endpoints

**Files:**
- Modify: `backend/src/koherent/routes/study.py`
- Test: `backend/tests/test_study.py`

**Interfaces:**
- Consumes: `generate` (Task 1/7), `SUMMARY_SYSTEM_PROMPT`/`REVIEW_SYSTEM_PROMPT`/`build_summary_prompt`/`build_review_prompt`/`ReviewItem` (Task 8), `is_anomaly` (existing `pipeline/report.py`), `LectureSummary` (Task 5), `load_lecture_for_student` (Task 6), schemas (Task 10).
- Produces: `POST /lectures/{id}/summary` (200 → `LectureSummaryRead`, regenerates and overwrites), `GET /lectures/{id}/summary` (200 cached / 404), `POST /lectures/{id}/review` (200 → `ReviewResponse`); 400 if lecture unprocessed (summary/review) or caller has no notes (review); 502 on generation failure.
- Weak-note rule (exact): weak = caller's notes where `is_anomaly(similarity, settings.anomaly_threshold)` is true (missing alignment counts as anomalous). If no weak notes, fall back to the caller's 3 lowest-similarity notes. `weak_note_count` = number of notes actually sent to the LLM.

- [ ] **Step 1: Write the failing tests** — `backend/tests/test_study.py`:

```python
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
        json={"content": "the mitochondria is the powerhouse of the cell", "client_timestamp_ms": 2000},
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `TEST_DATABASE_URL=... uv run pytest tests/test_study.py -v`
Expected: FAIL with 405s.

- [ ] **Step 3: Implement** — replace `routes/study.py` body:

```python
"""Lecture study artifacts: structured summaries and personalized review prompts.

The review endpoint is where the alignment layer pays off: a student's
anomalous / weakest notes — and what the transcript actually said at that
point — become the input for targeted review prompts, so the output is
personal, not generic.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from koherent.ai.base import AIClient
from koherent.config import settings
from koherent.deps import get_ai_client, get_current_student, get_db
from koherent.models import LectureSummary, Note, Student, TranscriptChunk
from koherent.pipeline.prompts import (
    REVIEW_SYSTEM_PROMPT,
    SUMMARY_SYSTEM_PROMPT,
    ReviewItem,
    build_review_prompt,
    build_summary_prompt,
)
from koherent.pipeline.report import is_anomaly
from koherent.routes.access import load_lecture_for_student
from koherent.schemas import LectureSummaryRead, ReviewResponse

router = APIRouter(prefix="/lectures", tags=["study"])

_REVIEW_FALLBACK_COUNT = 3


def _generate_or_502(ai: AIClient, system_prompt: str, user_prompt: str) -> str:
    try:
        return ai.generate(system_prompt, user_prompt)
    except Exception:
        raise HTTPException(status_code=502, detail="LLM generation failed")


@router.post("/{lecture_id}/summary", response_model=LectureSummaryRead)
def create_summary(
    lecture_id: uuid.UUID,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
    ai: AIClient = Depends(get_ai_client),
) -> LectureSummaryRead:
    lecture = load_lecture_for_student(lecture_id, current, db)
    if lecture.transcript is None:
        raise HTTPException(status_code=400, detail="Lecture has not been processed yet")
    chunks = list(
        db.scalars(
            select(TranscriptChunk)
            .where(TranscriptChunk.transcript_id == lecture.transcript.id)
            .order_by(TranscriptChunk.chunk_index)
        )
    )
    content = _generate_or_502(
        ai, SUMMARY_SYSTEM_PROMPT, build_summary_prompt(lecture.title, [c.content for c in chunks])
    )
    summary = lecture.summary
    if summary is None:
        summary = LectureSummary(
            lecture_id=lecture.id, content=content, model=settings.nim_chat_model
        )
        db.add(summary)
    else:
        summary.content = content
        summary.model = settings.nim_chat_model
    db.commit()
    db.refresh(summary)
    return LectureSummaryRead(
        lecture_id=lecture.id,
        content=summary.content,
        model=summary.model,
        created_at=summary.created_at,
    )


@router.get("/{lecture_id}/summary", response_model=LectureSummaryRead)
def get_summary(
    lecture_id: uuid.UUID,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
) -> LectureSummaryRead:
    lecture = load_lecture_for_student(lecture_id, current, db)
    if lecture.summary is None:
        raise HTTPException(status_code=404, detail="No summary generated yet")
    return LectureSummaryRead(
        lecture_id=lecture.id,
        content=lecture.summary.content,
        model=lecture.summary.model,
        created_at=lecture.summary.created_at,
    )


@router.post("/{lecture_id}/review", response_model=ReviewResponse)
def create_review(
    lecture_id: uuid.UUID,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
    ai: AIClient = Depends(get_ai_client),
) -> ReviewResponse:
    lecture = load_lecture_for_student(lecture_id, current, db)
    if lecture.transcript is None:
        raise HTTPException(status_code=400, detail="Lecture has not been processed yet")
    notes = list(
        db.scalars(
            select(Note).where(Note.lecture_id == lecture.id, Note.student_id == current.id)
        )
    )
    if not notes:
        raise HTTPException(status_code=400, detail="You have no notes in this lecture")

    def similarity_of(note: Note) -> float | None:
        return note.alignment.similarity if note.alignment is not None else None

    weak = [n for n in notes if is_anomaly(similarity_of(n), settings.anomaly_threshold)]
    if not weak:
        weak = sorted(notes, key=lambda n: similarity_of(n) or 0.0)[:_REVIEW_FALLBACK_COUNT]

    items = [
        ReviewItem(
            note_content=n.content,
            matched_content=n.alignment.chunk.content if n.alignment is not None else None,
            similarity=similarity_of(n),
        )
        for n in weak
    ]
    content = _generate_or_502(ai, REVIEW_SYSTEM_PROMPT, build_review_prompt(items))
    return ReviewResponse(
        lecture_id=lecture.id,
        content=content,
        weak_note_count=len(items),
        model=settings.nim_chat_model,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `TEST_DATABASE_URL=... uv run pytest tests/test_study.py -v` → all PASS. `uv run ruff check src tests`.

- [ ] **Step 5: Commit (orchestrator)**

```bash
git add backend/src/koherent/routes/study.py backend/tests/test_study.py
git commit -m "feat(api): lecture summaries and personalized review prompts"
```

---

### Task 14: Eval harness — metrics, golden set, report artifact

**Files:**
- Create: `backend/src/koherent/pipeline/metrics.py`
- Create: `backend/evals/__init__.py` (empty), `backend/evals/run_eval.py`, `backend/evals/golden.json`, `backend/evals/fixtures/econ_notes.md`
- Modify: `backend/pyproject.toml` (pytest `pythonpath = ["src", "."]`)
- Test: `backend/tests/test_metrics.py`, `backend/tests/test_eval_harness.py`
- Output: `backend/samples/eval_report.md` and `backend/samples/eval_report.json` (run artifacts, committed)

**Interfaces:**
- Consumes: `chunk_text` (Task 2), `chunk_transcript` (existing `pipeline/chunking.py`), `Candidate`/`top_k` (Task 4), prompts (Task 8), judge (Task 9), `FakeAIClient`/`RealAIClient`.
- Produces:
  - `hit_at_k(ranked_contents: list[str], marker: str, k: int) -> bool` — case-insensitive substring match within the top k.
  - `reciprocal_rank(ranked_contents: list[str], marker: str) -> float` — `1/rank` of the first match, else `0.0`.
  - `evals/run_eval.py` with `run_eval(ai, root: Path) -> dict` (pure-ish core; returns the results dict) and `main()` that picks Real vs Fake by `NVIDIA_API_KEY`, calls `run_eval`, and writes `samples/eval_report.{md,json}`.

- [ ] **Step 1: Write the failing metrics tests** — `backend/tests/test_metrics.py`:

```python
from koherent.pipeline.metrics import hit_at_k, reciprocal_rank


def test_hit_at_k_true_within_k():
    ranked = ["nothing here", "Elasticity measures responsiveness", "other"]
    assert hit_at_k(ranked, "elasticity", k=2) is True


def test_hit_at_k_false_outside_k():
    ranked = ["nothing here", "still nothing", "Elasticity measures"]
    assert hit_at_k(ranked, "elasticity", k=2) is False


def test_reciprocal_rank_of_first_match():
    ranked = ["miss", "miss", "Elasticity here"]
    assert reciprocal_rank(ranked, "elasticity") == 1 / 3


def test_reciprocal_rank_no_match_is_zero():
    assert reciprocal_rank(["a", "b"], "zzz") == 0.0
```

- [ ] **Step 2: Run to verify failure, then implement** — `backend/src/koherent/pipeline/metrics.py`:

Run: `uv run pytest tests/test_metrics.py -v` → `ModuleNotFoundError`.

```python
"""Retrieval metrics for the eval harness.

Golden queries carry a `marker` — a substring that must appear in a
retrieved chunk for it to count as the right chunk. Marker matching (not
chunk ids) keeps the golden set stable across re-chunking and re-embedding.
"""


def hit_at_k(ranked_contents: list[str], marker: str, k: int) -> bool:
    needle = marker.lower()
    return any(needle in content.lower() for content in ranked_contents[:k])


def reciprocal_rank(ranked_contents: list[str], marker: str) -> float:
    needle = marker.lower()
    for i, content in enumerate(ranked_contents):
        if needle in content.lower():
            return 1 / (i + 1)
    return 0.0
```

Run: `uv run pytest tests/test_metrics.py -v` → PASS.

- [ ] **Step 3: Author the fixture document** — `backend/evals/fixtures/econ_notes.md`: write a ~700-word intro-economics study document with headed sections (`# Supply and demand`, `# Elasticity`, `# Price controls`, `# Marginal analysis`, `# Market structures`, `# Externalities`), each section 90–130 words of substantive content (definitions, one worked example each). Every section must contain at least one distinctive multi-word phrase usable as a golden marker (e.g. "price elasticity of demand", "binding price ceiling", "marginal revenue equals marginal cost", "deadweight loss").

- [ ] **Step 4: Author the golden set** — `backend/evals/golden.json`. Exact format:

```json
{
  "queries": [
    {
      "id": "m1",
      "query": "What does price elasticity of demand measure?",
      "marker": "price elasticity of demand",
      "target": "material"
    }
  ]
}
```

Author 14 queries total: 7 with `"target": "material"` (answers live in distinct sections of `econ_notes.md`, marker = that section's distinctive phrase) and 7 with `"target": "transcript"` (read `backend/tests/fixtures/sample_transcript.json`, pick 7 content-bearing passages spread across the transcript, write a natural question for each, marker = a distinctive 2-4 word phrase from that passage). Rule: each query's marker must appear in exactly one region of its source so hit@k is meaningful; each query must share at least two content words with its target passage so the offline bag-of-words fake can retrieve it lexically.

- [ ] **Step 5: Write the failing harness test** — `backend/tests/test_eval_harness.py`:

```python
from pathlib import Path

from koherent.ai.fake import FakeAIClient

from evals.run_eval import run_eval

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def test_offline_eval_produces_full_results():
    results = run_eval(FakeAIClient(), BACKEND_ROOT)
    r = results["retrieval"]
    assert r["query_count"] == 14
    assert set(r) >= {"query_count", "hit_at_1", "hit_at_5", "mrr"}
    assert 0.0 <= r["mrr"] <= 1.0
    assert r["hit_at_5"] >= 0.5  # sanity gate: lexical overlap must be retrievable offline
    g = results["groundedness"]
    assert g["judged_query_count"] == 5
    assert g["unsupported_claim_rate"] is not None
    assert results["mode"] == "fake"
```

First update `backend/pyproject.toml` so tests can import the `evals` package:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src", "."]
addopts = "-ra -q"
```

Create empty `backend/evals/__init__.py`. Run: `uv run pytest tests/test_eval_harness.py -v` → FAIL (`No module named 'evals.run_eval'`).

- [ ] **Step 6: Implement the harness** — `backend/evals/run_eval.py`:

```python
"""Eval harness: retrieval metrics + LLM-judge groundedness over a golden set.

Corpus = the committed econ study document (text-chunked) + the committed
sample lecture transcript (time-chunked), embedded as passages. Each golden
query is embedded as a query, retrieved top-5, and scored by marker match
(hit@1, hit@5, MRR). The first 5 queries also run the full ask pipeline and
an LLM judge scores each answer's claims against the retrieved context —
the unsupported-claim rate is the hallucination measure.

Run:  uv run python evals/run_eval.py     (from backend/)
Real NVIDIA adapters when NVIDIA_API_KEY is set; FakeAIClient otherwise
(deterministic, disclosed in the report header).
"""
import json
import sys
import uuid
from pathlib import Path

from koherent.ai.base import TranscriptWord
from koherent.ai.fake import FakeAIClient
from koherent.config import settings
from koherent.pipeline.chunking import chunk_transcript
from koherent.pipeline.judge import (
    JUDGE_SYSTEM_PROMPT,
    build_judge_user_prompt,
    parse_judge_output,
    unsupported_rate,
)
from koherent.pipeline.metrics import hit_at_k, reciprocal_rank
from koherent.pipeline.prompts import (
    GROUNDED_SYSTEM_PROMPT,
    build_ask_prompt,
    build_context_block,
)
from koherent.pipeline.retrieval import Candidate, top_k
from koherent.pipeline.text_chunking import chunk_text

TOP_K = 5
JUDGED_QUERIES = 5


def _load_corpus(ai, root: Path) -> list[Candidate]:
    material_text = (root / "evals" / "fixtures" / "econ_notes.md").read_text()
    material_chunks = chunk_text(material_text)

    transcript_data = json.loads((root / "tests" / "fixtures" / "sample_transcript.json").read_text())
    words = [
        TranscriptWord(word=w["word"], start_ms=w["start_ms"], end_ms=w["end_ms"])
        for w in transcript_data["words"]
    ]
    transcript_chunks = chunk_transcript(words)

    texts = [c.content for c in material_chunks] + [c.content for c in transcript_chunks]
    vectors = ai.embed(texts)

    candidates: list[Candidate] = []
    for chunk, vector in zip(material_chunks, vectors[: len(material_chunks)]):
        candidates.append(
            Candidate(
                source="material",
                ref_id=uuid.uuid4(),
                label="econ_notes.md",
                content=chunk.content,
                vector=vector,
            )
        )
    for chunk, vector in zip(transcript_chunks, vectors[len(material_chunks) :]):
        candidates.append(
            Candidate(
                source="transcript",
                ref_id=uuid.uuid4(),
                label="sample_lecture",
                content=chunk.content,
                vector=vector,
            )
        )
    return candidates


def run_eval(ai, root: Path) -> dict:
    golden = json.loads((root / "evals" / "golden.json").read_text())["queries"]
    corpus = _load_corpus(ai, root)

    per_query = []
    for q in golden:
        ranked = top_k(ai.embed_query(q["query"]), corpus, k=TOP_K)
        contents = [r.content for r in ranked]
        per_query.append(
            {
                "id": q["id"],
                "query": q["query"],
                "target": q["target"],
                "hit_at_1": hit_at_k(contents, q["marker"], 1),
                "hit_at_5": hit_at_k(contents, q["marker"], TOP_K),
                "reciprocal_rank": reciprocal_rank(contents, q["marker"]),
                "top_score": ranked[0].score if ranked else None,
            }
        )

    judged = []
    for q in golden[:JUDGED_QUERIES]:
        ranked = top_k(ai.embed_query(q["query"]), corpus, k=TOP_K)
        block, _ = build_context_block(ranked, settings.context_char_budget)
        answer = ai.generate(GROUNDED_SYSTEM_PROMPT, build_ask_prompt(q["query"], block))
        verdict = parse_judge_output(
            ai.generate(JUDGE_SYSTEM_PROMPT, build_judge_user_prompt(answer, block))
        )
        judged.append({"id": q["id"], "answer": answer, "verdict": verdict})

    n = len(per_query)
    return {
        "mode": "fake" if isinstance(ai, FakeAIClient) else "real",
        "retrieval": {
            "query_count": n,
            "hit_at_1": sum(q["hit_at_1"] for q in per_query) / n,
            "hit_at_5": sum(q["hit_at_5"] for q in per_query) / n,
            "mrr": sum(q["reciprocal_rank"] for q in per_query) / n,
            "per_query": per_query,
        },
        "groundedness": {
            "judged_query_count": len(judged),
            "unsupported_claim_rate": unsupported_rate([j["verdict"] for j in judged]),
            "parse_error_count": sum(1 for j in judged if j["verdict"].parse_error),
            "answers": [
                {
                    "id": j["id"],
                    "answer": j["answer"],
                    "claims": [
                        {"text": c.text, "supported": c.supported} for c in j["verdict"].claims
                    ],
                    "parse_error": j["verdict"].parse_error,
                }
                for j in judged
            ],
        },
    }


def _write_report(results: dict, root: Path) -> None:
    samples = root / "samples"
    samples.mkdir(exist_ok=True)
    (samples / "eval_report.json").write_text(json.dumps(results, indent=2))

    r, g = results["retrieval"], results["groundedness"]
    lines = ["# Koherent eval report", ""]
    if results["mode"] == "fake":
        lines += [
            "> Generated with the deterministic FakeAIClient (no NVIDIA_API_KEY set).",
            "> Numbers demonstrate the harness, not real embedding quality.",
            "",
        ]
    lines += [
        "## Retrieval (golden set)",
        "",
        f"- Queries: {r['query_count']}",
        f"- hit@1: {r['hit_at_1']:.2f}",
        f"- hit@5: {r['hit_at_5']:.2f}",
        f"- MRR: {r['mrr']:.2f}",
        "",
        "| id | target | hit@1 | hit@5 | RR |",
        "|---|---|---|---|---|",
    ]
    for q in r["per_query"]:
        lines.append(
            f"| {q['id']} | {q['target']} | {q['hit_at_1']} | {q['hit_at_5']} "
            f"| {q['reciprocal_rank']:.2f} |"
        )
    rate = g["unsupported_claim_rate"]
    lines += [
        "",
        "## Groundedness (LLM-as-judge)",
        "",
        f"- Answers judged: {g['judged_query_count']}",
        f"- Unsupported-claim rate: {'n/a' if rate is None else f'{rate:.2f}'}",
        f"- Judge parse errors: {g['parse_error_count']}",
        "",
    ]
    (samples / "eval_report.md").write_text("\n".join(lines))


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    if settings.nvidia_api_key:
        from koherent.ai.chat import NIMChatClient
        from koherent.ai.embeddings import NIMEmbedder

        class _EvalAI:
            """Embeddings + chat only; eval never transcribes."""

            def __init__(self):
                self._embedder = NIMEmbedder()
                self._chat = NIMChatClient()

            def embed(self, texts):
                return self._embedder.embed(texts)

            def embed_query(self, text):
                return self._embedder.embed([text], input_type="query")[0]

            def generate(self, system_prompt, user_prompt):
                return self._chat.generate(system_prompt, user_prompt)

        ai = _EvalAI()
    else:
        ai = FakeAIClient()
    results = run_eval(ai, root)
    _write_report(results, root)
    r = results["retrieval"]
    print(
        f"mode={results['mode']} hit@1={r['hit_at_1']:.2f} hit@5={r['hit_at_5']:.2f} "
        f"mrr={r['mrr']:.2f} -> samples/eval_report.md"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Note: `run_eval`'s `mode` check treats any non-`FakeAIClient` as real — `_ExplodingAI` subclasses would report fake, which is fine (tests only use `FakeAIClient` here).

> **Verify the transcript fixture format before writing `_load_corpus`:** the code above assumes `sample_transcript.json` is `{"words": [{"word", "start_ms", "end_ms"}, ...]}`. Read how `backend/scripts/run_sample_report.py` loads the same file and mirror its exact key names — adjust `_load_corpus` if the real shape differs.

- [ ] **Step 7: Run tests + generate the artifact**

Run: `uv run pytest tests/test_metrics.py tests/test_eval_harness.py -v` → PASS. If `hit_at_5 >= 0.5` fails offline, revise golden queries to share more content words with their target passages (do NOT weaken the gate).
Run: `cd backend && uv run python evals/run_eval.py` — with `NVIDIA_API_KEY` in `backend/.env` this produces a **real** report (real embeddings + Llama judge); commit whatever mode ran, the header discloses it.
`uv run ruff check src tests evals`.

- [ ] **Step 8: Commit (orchestrator)**

```bash
git add backend/src/koherent/pipeline/metrics.py backend/evals backend/tests/test_metrics.py backend/tests/test_eval_harness.py backend/pyproject.toml backend/samples/eval_report.md backend/samples/eval_report.json
git commit -m "feat(evals): retrieval metrics + LLM-judge groundedness harness with committed report"
```

---

### Task 15: Documentation — wiki decisions, README, plan hygiene

**Files:**
- Modify: `docs/wiki/DECISIONS.md`, `docs/wiki/topics/07-ai-pipeline.md` (or create `docs/wiki/topics/08-assistant-and-evals.md` if 07 is transcription/embedding-focused — follow the wiki README's structure conventions)
- Modify: `README.md`
- Modify: `project_plan.md` — **DO NOT COMMIT this file** (it has unrelated uncommitted user edits; leave it in the working tree)

**Interfaces:** none — documentation of what Tasks 1–14 shipped.

- [ ] **Step 1: Read the current docs** — `docs/wiki/README.md`, `docs/wiki/DECISIONS.md`, `docs/wiki/topics/07-ai-pipeline.md`, and the repo `README.md`, to match voice and structure. Note the wiki's decision-entry format (D-NNN rows linked to topic pages).

- [ ] **Step 2: Record five new decisions** (next IDs after D-028; verify the last ID in DECISIONS.md and continue from it), each with the wiki's standard fields (context, decision, why, alternatives considered):
  - **Chat generation behind the same seam** — `generate()` on `AIClient`; NIM chat via OpenAI SDK transport; model configurable (`nim_chat_model`, default `meta/llama-3.3-70b-instruct`); temperature 0.2.
  - **Document ingestion & text chunking** — suffix-dispatch extraction (.txt/.md/.pdf via pypdf); paragraph-aware ~250-word chunks, 50-word overlap; separate module from time-based ASR chunking, and why.
  - **Query-typed retrieval** — `embed_query` with `input_type="query"` closes the documented embedqa asymmetry gap; top-k cosine scan in Python; pgvector still the scale path (extends D-025/D-026).
  - **Eval design** — marker-based golden set (substring match, not chunk ids) with hit@k/MRR; LLM-judge groundedness with strict-JSON parsing and explicit parse-error accounting; committed report artifact; framed as smoke metrics, not benchmarks.
  - **Report scoping / authz** — class-membership guard on process/report; report returns caller's own notes only; full-class view deferred to the professor role.

- [ ] **Step 3: Update README.md** — extend the pipeline narrative with the assistant layer (materials → chunks → embeddings → top-k retrieval → grounded generation with citations) and the eval harness (link `samples/eval_report.md`); move newly shipped items out of any "designed-next" list; add the new endpoints to any endpoint table; keep the honest "not built yet" section accurate (clustering dashboard, professor role, background jobs remain designed-next).

- [ ] **Step 4: Fix `project_plan.md` checkboxes** — tick only items that are demonstrably done in code as of this plan (capture app, ASR, chunking, embeddings, alignment, anomaly flag, report, and the new assistant/eval items if listed). Leave unbuilt items unchecked. **Do not stage or commit this file.**

- [ ] **Step 5: Verify docs render sanely** (headings, links) and internal links resolve. Run the full test suite one final time: `uv run pytest` → all PASS.

- [ ] **Step 6: Commit (orchestrator)**

```bash
git add docs/wiki README.md
git commit -m "docs: record assistant + eval layer decisions; update README narrative"
```

---

## Final integration (orchestrator)

- [ ] Full suite green from `backend/`: `uv run pytest` (all files), `uv run ruff check src tests evals`.
- [ ] `uv run alembic upgrade head` applied cleanly on the dev DB.
- [ ] Manual smoke (optional, requires key): start the API, upload a `.md`, `POST /ask`, confirm citations.
- [ ] Report to the user: what shipped, eval numbers, and that `project_plan.md` checkbox edits are left uncommitted for their review.
