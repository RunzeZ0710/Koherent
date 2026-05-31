# Week 2A — Retrieval Pipeline (design)

**Date:** 2026-05-30
**Status:** Approved (design); implementation plan to follow
**Scope:** Stages 1–4 of the Week 2 AI pipeline (transcription → chunking →
embedding → note-to-transcript alignment). Stages 5–7 (claim extraction,
LLM-as-judge, feedback report) are deferred to **Week 2B**.

This is the first of two sequential plans that together deliver all seven Week 2
stages from `project_plan.md`. Nothing from that list is dropped — it is split
for digestibility because the author is hand-writing the code to learn.

---

## Goal

When a lecture is done, a single call processes it: the audio is transcribed, the
transcript is sliced into ~30-second chunks, every chunk and every student note
is embedded into a vector, and each note is aligned to the transcript chunk it
most closely matches (by cosine similarity), with a similarity score. All of it
is persisted to Postgres.

**Done means:** `POST /lectures/{id}/process` runs end-to-end against the
`FakeAIClient` and, for a seeded lecture with notes + audio, produces a
transcript, transcript chunks (embedded), embedded notes, and one
`note_alignment` row per note (best-matching chunk + similarity) — all verified
in the database by tests.

**Explicitly NOT in this plan:** claim extraction, LLM-as-judge correctness
scoring, per-student feedback reports. Those are Week 2B.

---

## Working agreement (how we build it)

- **Learning mode: "you drive, I coach."** For each task: I explain the concept
  and the *why*, sketch the interface/signature, then the author writes the
  implementation; I review and we fix together; tests confirm. I write directly
  only the scaffolding/plumbing the author doesn't need to hand-write.
- **No NVIDIA key yet.** We build and test entirely against a fake AI client
  behind a stable interface, and swap in the real NVIDIA NIM client later by
  filling in the same two methods. This is deliberate, not a workaround (see
  "The seam" below).

---

## Key design decision: the AIClient seam

All AI work hides behind one interface. The pipeline depends only on this
interface, never on NVIDIA directly.

```python
class AIClient(Protocol):
    def transcribe(self, audio_path: str) -> str: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

Two implementations:

- **`FakeAIClient`** — deterministic, instant, no network. Canned transcripts and
  toy-but-deterministic embeddings. This is what we build and test against now.
- **`NIMClient`** — the real adapter calling NVIDIA's hosted NIM endpoints.
  Written later (a stub with `NotImplementedError` lands in this plan to prove
  the seam compiles); filled in when an `nvapi-…` key exists.

**Why this matters:** this is the ports-and-adapters / dependency-inversion
pattern. It makes the project's V1→V2 migration story literally true — "I swapped
one adapter behind a stable interface; the pipeline code did not change." It also
unblocks all of Week 2A with no API key.

The client is injected via FastAPI dependency injection (same mechanism as
`get_db` in Week 1), so tests force the fake and real runs would use `NIMClient`.

---

## Data model (new)

One new Alembic migration (`0002`). Three new tables and one new column on the
existing `notes` table. Embeddings are stored as plain `float[]` array columns;
cosine similarity is computed in Python (numpy) — no `pgvector` extension. At our
scale (≤30 students × a few hundred vectors) this is ample, keeps the math
visible and hand-writable, and a later migration to `pgvector` is itself a good
engineering story.

**`transcripts`** — one per lecture (the ASR output).

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `lecture_id` | UUID FK → lectures, **unique** | one transcript per lecture; `ondelete=CASCADE` |
| `full_text` | text | the raw transcript |
| `created_at` | timestamptz | server default now |

**`transcript_chunks`** — the transcript sliced into ~30s embedded pieces.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `transcript_id` | UUID FK → transcripts | `ondelete=CASCADE`, indexed |
| `chunk_index` | int | 0, 1, 2, … ordering within the transcript |
| `content` | text | the chunk's text |
| `start_ms` | bigint | chunk start, ms from lecture start |
| `end_ms` | bigint | chunk end, ms from lecture start |
| `embedding` | float[] | the chunk's vector |
| `created_at` | timestamptz | |

**`notes`** — two new columns (both nullable; populated during processing):

| Column | Type | Notes |
|--------|------|-------|
| `embedding` | float[] | the note's vector (null until processed) |

(Only `embedding` is added to `notes`. The alignment result lives in its own
table — see below.)

**`note_alignments`** — derived result: each note's best-matching chunk.

| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID PK | |
| `note_id` | UUID FK → notes, **unique** | one alignment per note; `ondelete=CASCADE` |
| `transcript_chunk_id` | UUID FK → transcript_chunks | `ondelete=CASCADE` |
| `similarity` | float | cosine similarity, 0–1, of the match |
| `created_at` | timestamptz | |

**Why `note_alignments` is its own table** (not columns on `notes`): alignment is
a *derived* result that is recomputed on every reprocess. Keeping it separate
means re-running the pipeline clears and rebuilds this table without touching the
raw notes. Separating raw input from derived output is the pattern being taught.

---

## Module layout

A new `ai/` package (the seam) and `pipeline/` package (the stages) keep the AI
work cleanly separated from the Week 1 CRUD code.

```
backend/src/koherent/
  ai/
    base.py          # the AIClient Protocol (the seam)
    fake.py          # FakeAIClient — deterministic, instant
    nim.py           # NIMClient — real NVIDIA adapter (stub for now)
  pipeline/
    chunking.py      # split transcript text -> ~30s time-stamped chunks
    alignment.py     # cosine similarity: note vec vs chunk vecs -> best match
    process.py       # orchestrator: ties the 4 stages together
  routes/
    processing.py    # POST /lectures/{id}/process
```

`chunking.py` and `alignment.py` are small, pure, independently testable units —
the two pieces the author hand-writes. `process.py` only orchestrates; it holds
no clever logic of its own.

---

## Pipeline flow (`POST /lectures/{id}/process`)

Synchronous: the endpoint runs the whole pipeline inline and returns when done.
(Simple to write, test, and reason about; the fake client is instant. A
background-job upgrade is possible later if real processing gets slow.)

```
1. transcribe   audio file ──AIClient.transcribe()──> transcript text  ─> save Transcript
2. chunk        transcript text ──chunking.py───────> list of chunks    ─> save TranscriptChunks
3. embed        chunk texts + note texts ──AIClient.embed()──> vectors  ─> save embeddings
4. align        each note vec vs all chunk vecs ──alignment.py──> best  ─> save NoteAlignments
                                                                         ─> 200 OK
```

Reprocessing is idempotent: a re-run clears this lecture's derived rows
(transcript, chunks, alignments, note embeddings) and rebuilds them.

---

## Testing strategy

Same discipline as Week 1: real Postgres test DB, transactional rollback per
test, TDD. The `AIClient` seam makes the whole pipeline testable with no network
and no flakiness.

- **`FakeAIClient`** returns deterministic vectors, so similarity outcomes are
  predictable and tests can assert exact alignments.
- **`chunking.py` unit tests:** feed known text + duration; assert chunk
  boundaries, ordering, and `start_ms`/`end_ms`.
- **`alignment.py` unit tests:** feed hand-picked vectors whose nearest neighbor
  is obvious (e.g. `[1,0]`, `[0,1]`, `[0.9,0.1]`); assert the match and the score.
  The author verifies the cosine math by hand first, then the test confirms it.
- **Integration test for `POST /lectures/{id}/process`:** seed a lecture + notes
  + audio, call the endpoint, assert transcript, chunks, note embeddings, and
  one alignment per note all persisted with sane values.
- **Injection:** the `FakeAIClient` is provided via FastAPI dependency override
  (same trick as `get_db`); real runs would resolve `NIMClient`.

---

## Task breakdown (order)

Each task is a "you drive, I coach" cycle.

1. **The `AIClient` seam** — `ai/base.py` Protocol + `ai/fake.py` `FakeAIClient`.
   (Mostly authored by the coach; it's scaffold.) Teaches: interfaces/Protocols,
   dependency inversion.
2. **Data model + migration** — 3 tables, 1 new `notes` column, Alembic `0002`.
   Coach-heavy; builds on Week 1 models.
3. **`chunking.py`** — author writes it, TDD. Teaches: text segmentation,
   timestamp math.
4. **`alignment.py`** — author writes it, TDD. Teaches: embeddings, cosine
   similarity, argmax. The centerpiece.
5. **`process.py` + `POST /lectures/{id}/process`** — wire the 4 stages;
   integration test; idempotent reprocess.
6. **`NIMClient` stub** — real-adapter shell raising `NotImplementedError`, with a
   note on what goes in when the key arrives. Proves the seam.
7. **Wiki update** — record the new decisions (D-023+) in `docs/wiki/` under the
   existing framework.

---

## Risks / notes

- **Alignment quality is fuzzy by nature** (the plan flags this). With the fake
  client it's deterministic; real quality only shows once `NIMClient` is wired and
  a real key exists. Week 2A proves the *machinery*, not real-world accuracy.
- **Fixed 30s chunking is the starting point** per `project_plan.md`; refine to
  topic-shift detection later only if alignment is too noisy.
- **`float[]` + Python similarity is a deliberate scale-appropriate choice;** the
  later `pgvector` migration is intended as part of the V2 story, not a correction.
