# 07 — The AI Retrieval Pipeline

> **Decisions on this page:** [D-023](#d-023-hide-all-ai-behind-one-aiclient-seam),
> [D-024](#d-024-transcribe-returns-a-transcription-text--word-timestamps),
> [D-025](#d-025-embeddings-via-nvidia-nim-nv-embedqa-e5-v5),
> [D-026](#d-026-store-vectors-as-float-columns-cosine-in-python-no-pgvector),
> [D-027](#d-027-link-by-cosine-argmax-flag-anomalies-below-a-threshold),
> [D-028](#d-028-process-synchronously-and-idempotently)

This page covers how a finished lecture becomes linked, scored data: audio →
transcript → chunks → vectors → note-to-chunk links → anomaly flags.

---

## 1. The concepts from zero

### What is an embedding, and why cosine similarity?

An **embedding** turns a piece of text into a list of numbers (a vector) such that
texts with similar *meaning* land near each other in space. "Credit card fees hurt
small businesses" and "merchants lose money to card processing" point in nearly the
same direction even though they share few words.

To measure "same direction" we use **cosine similarity** — the cosine of the angle
between two vectors: `1.0` = identical direction, `0` = unrelated, `-1` = opposite.
It ignores length and looks only at direction, which is what we want when comparing
a short note to a longer transcript chunk. The whole of
[`alignment.py`](../../../backend/src/koherent/pipeline/alignment.py) is this one
idea plus an argmax.

### What is "the seam"?

The pipeline needs three external AI capabilities (speech-to-text, embeddings) that
are slow, networked, and cost money. If pipeline code called NVIDIA directly,
nothing could be tested without a key and a network, and swapping providers would
mean rewriting everything.

Instead we define **one interface** — a Python `Protocol` called `AIClient` — that
says "an AI backend can `transcribe` and `embed`." The pipeline depends only on that
interface. Two classes implement it: a fake one (instant, deterministic, offline)
and a real one (NVIDIA). This is the **ports-and-adapters** (a.k.a. dependency
inversion) pattern: the core logic talks to a *port*, and the *adapters* plug in
behind it.

### What does "retrieval" mean here?

Given a student note ("the query") we **retrieve** the transcript chunk it most
likely refers to ("the best passage"). It's the same machinery as search and as
the retrieval step of RAG, applied to a teaching feedback loop: which thing the
professor said does this note correspond to, and how confidently?

---

## 2. What we chose

**[D-023] All AI hides behind one `AIClient` seam.** The pipeline imports the
`AIClient` Protocol from [`ai/base.py`](../../../backend/src/koherent/ai/base.py)
and nothing else AI-related. `FakeAIClient`
([`ai/fake.py`](../../../backend/src/koherent/ai/fake.py)) returns deterministic
canned transcripts and bag-of-words vectors; `RealAIClient`
([`ai/real.py`](../../../backend/src/koherent/ai/real.py)) composes the Riva ASR
adapter and the NIM embedder. The client is injected with FastAPI dependency
injection (the same mechanism as `get_db`, see
[01-fastapi → D-004](01-fastapi.md#d-004-use-dependency-injection-for-db-and-auth)),
so tests force the fake and real runs resolve the NVIDIA one. The entire pipeline
is therefore testable with no network and no key.

**[D-024] `transcribe()` returns a `Transcription`, not a bare string.** Chunking
needs to slice the transcript by *time*, which requires per-word timestamps. So the
seam returns a `Transcription(text, words)` where each `TranscriptWord` carries
`start_ms`/`end_ms`. The fake client synthesizes timestamps at a fixed cadence so
the exact same chunking code runs on fake and real data.

**[D-025] Embeddings come from NVIDIA NIM `nv-embedqa-e5-v5`.** NIM exposes an
OpenAI-compatible endpoint, so the adapter
([`ai/embeddings.py`](../../../backend/src/koherent/ai/embeddings.py)) uses the
OpenAI SDK pointed at NVIDIA's base URL — all NVIDIA specifics contained in that one
file. For the MVP both chunks and notes are embedded with `input_type="passage"`;
embedding notes as `"query"` (the asymmetric retrieval mode these models support) is
a documented refinement.

**[D-026] Vectors are stored as Postgres `float[]` columns and cosine is computed
in Python.** At our scale (≤30 students × a few hundred vectors per lecture) a plain
array column plus a Python loop is ample, keeps the math visible and hand-written,
and avoids a database extension. Migrating to `pgvector` for indexed similarity
search is itself a planned engineering story, not a correction.

**[D-027] Notes link by cosine argmax; anomalies are matches below a threshold.**
`align()` gives each note the single chunk with the highest cosine similarity. A
note is an **anomaly** when that best similarity is below `anomaly_threshold`
(default `0.45`) — i.e. it doesn't clearly correspond to anything the lecture said.
The threshold was **calibrated against real `nv-embedqa-e5-v5` output**, where
on-topic notes scored ~0.54–0.67 and an off-topic note ~0.37; `0.45` cleanly
separates them. It's a tunable starting point and the seed of cross-student
misconception detection.

**[D-028] Processing is synchronous and idempotent.**
`POST /lectures/{id}/process` runs the four stages inline and returns when done —
simple to write, test, and reason about (the fake client is instant). Re-running
clears the lecture's derived rows (transcript → cascades chunks; alignments) and
rebuilds them, so processing twice yields the same state. A background-job upgrade
is possible later if real processing gets slow.

---

## 3. What we rejected, and why

- **Calling NVIDIA directly from the pipeline.** Untestable without a key and a
  network, and provider-locked. The seam makes the whole pipeline runnable offline
  and swappable.
- **A bare-string transcript.** Loses the word timestamps that time-based chunking
  needs; we'd have to re-derive timing elsewhere. Returning a `Transcription`
  keeps timing where it's produced.
- **`pgvector` from day one.** Real and the eventual right answer at scale, but
  premature now — it adds an extension and hides the similarity math the project is
  meant to demonstrate. Plain `float[]` + Python cosine is honest for the data size.
- **A background task queue (Celery/RQ) for processing.** Operationally heavier
  than a hard interview-deadline MVP needs while the fake client is instant and real
  runs are short. Synchronous now; revisit if latency demands it.
- **Treating low similarity as "wrong."** Embedding distance catches *off-topic*,
  not *false*. We say so explicitly rather than overclaim; factual correctness is
  the deferred LLM-as-judge layer's job.

---

## 4. In our code

| Thing | Where |
|-------|-------|
| The seam (Protocol + types) | [`ai/base.py`](../../../backend/src/koherent/ai/base.py) |
| Deterministic offline client | [`ai/fake.py`](../../../backend/src/koherent/ai/fake.py) |
| Real NVIDIA composite | [`ai/real.py`](../../../backend/src/koherent/ai/real.py) |
| Riva ASR adapter | [`ai/riva.py`](../../../backend/src/koherent/ai/riva.py) |
| NIM embeddings adapter | [`ai/embeddings.py`](../../../backend/src/koherent/ai/embeddings.py) |
| Chunking | [`pipeline/chunking.py`](../../../backend/src/koherent/pipeline/chunking.py) |
| Cosine + alignment | [`pipeline/alignment.py`](../../../backend/src/koherent/pipeline/alignment.py) |
| Anomaly rule | [`pipeline/report.py`](../../../backend/src/koherent/pipeline/report.py) |
| Orchestrator | [`pipeline/process.py`](../../../backend/src/koherent/pipeline/process.py) |
| Endpoints | [`routes/processing.py`](../../../backend/src/koherent/routes/processing.py) |
| Sample-report generator | [`scripts/run_sample_report.py`](../../../backend/scripts/run_sample_report.py) |

---

## 5. Decision records

### D-023: Hide all AI behind one `AIClient` seam

- **Date:** 2026-06-29
- **Status:** Active
- **Context:** AI calls are slow, networked, and paid; the pipeline must be testable
  and provider-swappable.
- **Decision:** Define an `AIClient` Protocol (`transcribe`, `embed`); the pipeline
  depends only on it. Inject a `FakeAIClient` for tests and a `RealAIClient`
  (Riva + NIM) for real runs via FastAPI DI.
- **Why:** Ports-and-adapters — the whole pipeline runs offline and deterministically,
  and changing backends touches one injected dependency.
- **Alternatives rejected:** Calling NVIDIA directly (untestable, provider-locked).

### D-024: `transcribe()` returns a `Transcription` (text + word timestamps)

- **Date:** 2026-06-29
- **Status:** Active
- **Context:** Time-based chunking needs per-word timestamps.
- **Decision:** The seam returns `Transcription(text, words)` with `start_ms`/`end_ms`
  per word; the fake client synthesizes a fixed cadence.
- **Why:** The same chunking code runs identically on fake and real transcripts.
- **Alternatives rejected:** Returning a bare string (loses timing).

### D-025: Embeddings via NVIDIA NIM `nv-embedqa-e5-v5`

- **Date:** 2026-06-29
- **Status:** Active
- **Context:** We need batched text embeddings behind the seam.
- **Decision:** Use NIM's OpenAI-compatible embeddings endpoint via the OpenAI SDK,
  isolated in one adapter; embed everything as `passage` for the MVP.
- **Why:** Keeps NVIDIA specifics in one file; reuses a standard SDK.
- **Alternatives rejected:** A bespoke HTTP client (more code, no benefit);
  query/passage split (a noted refinement, not needed yet).

### D-026: Store vectors as `float[]` columns, cosine in Python (no pgvector)

- **Date:** 2026-06-29
- **Status:** Active
- **Context:** Small scale (≤30 students × a few hundred vectors per lecture).
- **Decision:** Persist embeddings as Postgres `float[]`; compute cosine in a plain
  Python loop.
- **Why:** Ample at this scale, no extension, keeps the similarity math visible. A
  later `pgvector` migration is a planned story.
- **Alternatives rejected:** `pgvector` now (premature; hides the math).

### D-027: Link by cosine argmax; flag anomalies below a threshold

- **Date:** 2026-06-29
- **Status:** Active
- **Context:** Each note should map to the lecture span it refers to, and notes that
  match nothing should be surfaced.
- **Decision:** `align()` picks the highest-cosine chunk per note; a best similarity
  below `anomaly_threshold` (default `0.45`, calibrated against real `nv-embedqa`
  output) marks an anomaly.
- **Why:** Simple, explainable retrieval; the anomaly flag seeds misconception
  detection. The threshold is empirical and tunable.
- **Alternatives rejected:** Treating low similarity as "factually wrong" (embeddings
  match topic, not truth — that's the deferred LLM-judge's job).

### D-028: Process synchronously and idempotently

- **Date:** 2026-06-29
- **Status:** Active
- **Context:** A lecture must be turned into persisted derived data with a single call.
- **Decision:** `POST /lectures/{id}/process` runs all four stages inline; re-running
  clears and rebuilds the lecture's derived rows.
- **Why:** Simple to write/test/reason about; the fake client is instant and real runs
  are short. Idempotency makes reprocessing safe.
- **Alternatives rejected:** A background task queue (operationally heavier than the
  deadline needs right now).
