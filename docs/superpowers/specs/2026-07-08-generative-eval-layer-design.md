# Koherent — Generative + Eval Layer (design)

**Date:** 2026-07-08
**Status:** Approved (design); implementation plan to follow
**Driver:** Get to an MVP that truthfully supports three resume claims:
retrieval **and evaluation** workflows (RAG, embeddings, vector search);
an assistant that **ingests course materials** and generates **structured
summaries, concept explanations, and personalized review prompts** for a
20+ person class; FastAPI APIs that **process uploaded documents**, chunk,
retrieve context, and **generate responses through LLM inference endpoints**.

This spec sits on top of
[`2026-06-29-koherent-portfolio-mvp-design.md`](2026-06-29-koherent-portfolio-mvp-design.md).
The capture + retrieval-alignment slice it defined is shipped: audio →
Riva ASR → 30s chunks → NIM embeddings → cosine-argmax note linking →
anomaly flag → `/report`. This spec adds the layers that are currently
absent: **LLM generation, document ingestion, top-k retrieval, and an
evaluation workflow** — API-first, no new frontend.

---

## Why this scope

Exploration (2026-07-08) found the gaps precisely:

- The `AIClient` seam has only `transcribe` + `embed`. **No LLM generation
  exists anywhere** — no chat call, no prompt template, no summary code.
- Ingestion is **audio-only**. No PDF/text/markdown path exists.
- Retrieval is cosine **top-1** (argmax per note); no top-k, and both notes
  and chunks are embedded as `input_type="passage"` despite the model's
  query/passage asymmetry (documented refinement in `embeddings.py:5-7`).
- There is **no eval harness** — no golden set, no metrics, no judge. The
  sample-report script is qualitative only.
- Authz hole: `POST /lectures/{id}/process` and `GET /lectures/{id}/report`
  skip the class-membership check every other lecture route performs, and
  `/report` returns **all** students' notes to any student.

Everything missing plugs into existing seams. NVIDIA NIM serves chat models
at the same endpoint (`https://integrate.api.nvidia.com/v1`) with the same
`NVIDIA_API_KEY` and the same OpenAI SDK transport already used for
embeddings — so the generative layer needs no new vendor, key, or SDK.

**Explicitly NOT in this MVP:** cross-student misconception clustering (the
Week 3 dashboard), any new frontend UI, background jobs/queues, pgvector.
Same honesty-first framing as the previous spec: these stay designed-next.

---

## What we build (dependency order)

### 1. `generate()` on the AI seam

Extend the `AIClient` protocol (`ai/base.py`) with:

```python
def generate(self, system_prompt: str, user_prompt: str) -> str: ...
```

- **Real:** `NIMChatClient` (`ai/chat.py`) using the OpenAI SDK against
  `https://integrate.api.nvidia.com/v1`, model from new setting
  `nim_chat_model` (default `meta/llama-3.3-70b-instruct`), temperature 0.2.
  Composed into `RealAIClient` alongside Riva + NIMEmbedder. Raises
  `ValueError` without `nvidia_api_key`, matching the existing adapters.
- **Fake:** deterministic `generate` on `FakeAIClient` — echoes a stable,
  template-shaped response derived from the prompts (hash-suffixed so tests
  can assert determinism and prompt-sensitivity). Whole test suite stays
  offline, zero keys.

### 2. Course-materials ingestion

New class-scoped tables (Alembic `0003_materials`):

- `materials` — id (UUID), class_id FK (CASCADE), filename, media_type,
  size_bytes, extracted_chars, created_at.
- `material_chunks` — id, material_id FK (CASCADE), chunk_index, content,
  `embedding ARRAY(Float)` NOT NULL.

Endpoints (`routes/materials.py`):

- `POST /classes/{class_id}/materials` — multipart upload; accepts
  `.txt`, `.md`, `.pdf` (pypdf for extraction); 415 otherwise; 422 if
  extraction yields empty text. Synchronously: extract → chunk → embed
  (`input_type="passage"`) → persist. Caller must belong to the class.
- `GET /classes/{class_id}/materials` — list (id, filename, chunk count).

New **text chunker** (`pipeline/text_chunking.py`), separate from the 30s
audio chunker: paragraph-aware word windows, ~250 words per chunk with
~50-word overlap; short paragraphs merge, long paragraphs split. Pure
function, unit-tested like `chunk_transcript`.

### 3. Retrieval module (top-k, query-typed)

`pipeline/retrieval.py`:

```python
def retrieve(query_vector, chunks, k=5) -> list[ScoredChunk]
```

- Cosine top-k (reuses `alignment.cosine`) over a class's material chunks
  plus transcript chunks; each result carries source (material|transcript),
  ids, content, span/filename, and score.
- Queries are embedded with `input_type="query"` — `NIMEmbedder.embed`
  gains an `input_type` parameter, closing the documented asymmetry gap.
  Note/chunk *passage* embedding paths are unchanged (no re-embedding).
- Plain Python loop stays (a class's corpus is thousands of chunks at
  most); pgvector remains the documented scale path (wiki D-026).

### 4. Generative endpoints (`routes/assistant.py`)

All are RAG-grounded: retrieve top-k → assemble a numbered-context prompt →
`generate()` with a system prompt instructing *answer only from the provided
context; say "not covered in the materials" otherwise; cite context numbers*.
All return the generated text **plus the citations** (chunk refs + scores).
All require class membership; 400 if the class has no indexed content yet.

- `POST /classes/{id}/ask` `{question}` — free-form Q&A over materials +
  transcripts. The canonical RAG loop.
- `POST /classes/{id}/explain` `{concept}` — concept explanation: retrieval
  on the concept term, generation prompt asks for definition → intuition →
  example, grounded in the retrieved context.
- `POST /lectures/{id}/summary` — structured summary of that lecture's
  transcript chunks (overview, key concepts, section-by-section bullets).
  Cached: result stored in new `lecture_summaries` table (lecture_id
  unique, content, model, created_at — included in migration `0003`).
  `POST` generates and overwrites (idempotent, same pattern as `/process`);
  `GET /lectures/{id}/summary` returns the cached row, 404 if none yet.
- `POST /lectures/{id}/review` — **the differentiator.** Loads the
  *caller's* notes with their alignments; selects anomalous/low-similarity
  ones (plus lecture chunks no note of theirs matched); generates
  personalized review prompts — per weak spot: what the lecture actually
  said, and 1-2 check-yourself questions. Grounded in the matched chunks,
  scoped strictly to the calling student.

Prompt templates live in `pipeline/prompts.py` as pure functions
(unit-testable string builders, no I/O).

### 5. Evaluation workflow (`backend/evals/`)

- `evals/golden.json` — golden dataset: ~15-20 queries with expected
  chunk labels, built from the existing `sample_transcript.json` plus one
  committed fixture document (`evals/fixtures/econ_notes.md`).
- `evals/run_eval.py` — the harness:
  1. **Retrieval metrics:** for each golden query, run `retrieve()`;
     compute hit@1, hit@5, MRR against expected labels.
  2. **Groundedness (LLM-as-judge):** for ~5 of the golden queries, run the
     full ask pipeline; judge prompt receives answer + retrieved context
     and returns per-claim `supported|unsupported` verdicts (strict JSON);
     report the unsupported-claim rate — the hallucination measure.
  3. Writes `samples/eval_report.md` (+ `.json`) — committed artifact in
     the style of `samples/sample_report.md`, with a fake-client
     disclosure header when run without a key.
- Judge-output parsing is a pure function with unit tests; the harness
  runs deterministically offline via `FakeAIClient`.

### 6. Hardening (part of this slice, not optional)

- Add the class-membership check (`_load_lecture_for_student` pattern) to
  `/process` and `/report`; 403 on cross-class access.
- Scope `/report` to the **caller's own notes** (transcript metadata stays
  shared). The full-class view returns when the professor role lands (out
  of scope here, consistent with the deferred professor auth).
- All new endpoints take the same membership guard from day one.

### 7. Docs

- Wiki decisions (D-029+): chat model choice & seam shape; text-chunking
  parameters; query-vs-passage input types; eval design (golden set +
  judge); report scoping fix.
- README: move shipped items out of "designed-next"; add the assistant +
  eval sections to the pipeline narrative.
- `project_plan.md`: tick the checkboxes that are actually done (checklist
  currently contradicts reality).

---

## Error handling

- Upload: 415 non-supported media type, 422 empty/unextractable text,
  existing 401/403 auth pattern everywhere.
- Generation: NIM failure or timeout → 502 with a short detail string; no
  retries in v1 (documented).
- Context assembly truncates to a character budget (~12k chars) before the
  model call; truncation is logged in the response metadata.

## Testing

Repo-convention TDD (D-016..018): pure unit tests for text chunker,
pdf/text extraction dispatch, top-k retrieval (ordering, ties, k > n),
prompt builders, judge-output parsing; route tests for materials/ask/
explain/summary/review/authz against real Postgres with `FakeAIClient`
override; eval harness smoke test (runs offline end-to-end, produces a
report). Real NIM chat adapter follows the existing pattern: pure
response-mapper unit-tested, network path exercised manually.

## Risks

- **Synchronous processing** (upload-time embedding, request-time
  generation) blocks workers under load — accepted for class scale,
  consistent with D-028; queue remains the documented next step.
- **Judge reliability:** LLM-as-judge on a small golden set is a smoke
  metric, not a benchmark; report frames it as such.
- **Model availability:** `nim_chat_model` is a setting so a deprecated
  NIM model id is a one-line fix.
