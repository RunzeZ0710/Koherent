# 08 — The Assistant, Ingestion & Eval Layer

> **Decisions on this page:** [D-029](#d-029-chat-generation-behind-the-same-seam),
> [D-030](#d-030-document-ingestion--text-chunking),
> [D-031](#d-031-query-typed-retrieval),
> [D-032](#d-032-eval-design),
> [D-033](#d-033-report-scoping--authz)

Topic [07](07-ai-pipeline.md) covers turning one lecture into linked, scored data.
This page covers what sits on top of that: a second corpus (uploaded course
materials, not just transcripts), an LLM that can *answer* instead of only
*embed*, the retrieval-and-generation loop that ties them together, the eval
harness that checks whether any of it actually works, and the authorization
hardening that came with exposing more class-scoped surface area.

---

## 1. The concepts from zero

### What is RAG, concretely?

"Retrieval-augmented generation" is two steps glued together: **retrieve** the
handful of passages most relevant to a question (topic 07's retrieval idea,
applied to a live question instead of a stored note), then **generate** an
answer by handing an LLM only those passages and instructing it to answer
*from them alone*. The point is to stop the model from answering out of its
own training data (which the professor never said and can't verify) and force
every claim back to a citable source. "Grounded" is the word for an answer
built this way.

### Why does an embedding model need a "query" mode?

Some embedding models are trained **asymmetrically**: they learn one encoding
for short questions ("queries") and a different encoding for the longer
passages being searched, because a question and its answer don't look alike
as strings even when they mean the same thing. `nv-embedqa-e5-v5` is one of
these — its name says so (`qa` = query/answer). Embedding both sides the same
way (as topic 07's MVP did) works but leaves quality on the table; asking for
the model's query encoding on the question side is a small change with a real
payoff.

### What is an eval harness, and why "smoke metrics, not benchmarks"?

An eval harness answers "did I just break retrieval or generation?" without a
human re-reading transcripts by hand. It needs a fixed set of questions with a
known-correct-ish answer (the **golden set**), a way to score each answer
automatically, and a report to look at. Fourteen questions over one small
corpus is not a benchmark — it can't support a claim like "87% accurate" in
any generalizable sense. It *can* support "hit@5 didn't regress" and "here is
a real, inspectable example of what the judge flagged." Calling it what it is
(a smoke test) rather than what it isn't (a benchmark) is itself a decision.

---

## 2. What we chose

**[D-029] Chat generation lives behind the same `AIClient` seam.** `generate(system_prompt, user_prompt) -> str` joins `transcribe`/`embed`/`embed_query` on the
[`AIClient`](../../../backend/src/koherent/ai/base.py) Protocol.
[`ai/chat.py`](../../../backend/src/koherent/ai/chat.py)'s `NIMChatClient`
implements it via the OpenAI SDK against NIM's chat-completions endpoint,
model configurable through `nim_chat_model` (default
`meta/llama-3.3-70b-instruct`), temperature fixed at `0.2`. `RealAIClient` now
composes three adapters (Riva, `NIMEmbedder`, `NIMChatClient`); `FakeAIClient.generate`
returns deterministic tagged text — except when the system prompt contains the
literal string `"Return ONLY JSON"` (every judge prompt does), in which case it
returns parseable JSON so the eval harness runs fully offline.

**[D-030] Document ingestion and chunking are a new, separate pipeline stage.**
[`pipeline/extraction.py`](../../../backend/src/koherent/pipeline/extraction.py)
dispatches by filename **suffix**, not browser-supplied MIME type (browsers are
unreliable about `.md`): `.txt`/`.md` decode as UTF-8, `.pdf` extracts via
`pypdf`. Unsupported suffixes raise `UnsupportedDocumentError` (→ 415); no
extractable text (empty file, scanned/image-only PDF, corrupt PDF) raises
`EmptyDocumentError` (→ 422) rather than silently ingesting blank chunks.
[`pipeline/text_chunking.py`](../../../backend/src/koherent/pipeline/text_chunking.py)
is deliberately **not** a generalization of `pipeline/chunking.py` (topic 07's
time-bucket ASR chunker): documents have no timeline, so chunking windows by
**word count** instead — packing whole paragraphs up to ~250 words, and
splitting any single paragraph that alone exceeds the target into overlapping
50-word windows so an idea is never cut with zero shared context.

**[D-031] Retrieval queries are embedded with `input_type="query"`, closing the
gap D-025 flagged.** The seam gained `embed_query(text) -> vector`, distinct
from `embed(texts)`. `NIMEmbedder`/`RealAIClient` call NIM with
`input_type="query"` for `embed_query` and `input_type="passage"` (the
existing default) for `embed`; `FakeAIClient.embed_query` returns the same
hashed bag-of-words vector as `embed` — a symmetric fake, which is fine
because the tests it supports assert shape and behavior, not model quality.
[`pipeline/retrieval.py`](../../../backend/src/koherent/pipeline/retrieval.py)'s
`top_k` scans a class's material + transcript chunks with a plain Python
cosine loop, reusing `pipeline/alignment.py`'s `cosine` — the exact "no
pgvector yet" reasoning of [D-026](07-ai-pipeline.md#d-026-store-vectors-as-float-columns-cosine-in-python-no-pgvector).
This decision **extends** [D-025](07-ai-pipeline.md#d-025-embeddings-via-nvidia-nim-nv-embedqa-e5-v5)
and D-026 rather than replacing them: same model, same storage, now used
asymmetrically the way it was designed for.

**[D-032] Eval design: marker-based golden set, hit@k/MRR, and a strict-JSON
LLM judge — explicitly framed as smoke metrics.**
[`backend/evals/golden.json`](../../../backend/evals/golden.json) holds 14
queries (7 targeting the committed econ course-material doc, 7 targeting the
committed sample lecture transcript). Each carries a `marker` — a **substring**
that must appear in a retrieved chunk to count as a hit — instead of a chunk
id, because ids break the moment chunking or embedding changes and a substring
does not.
[`pipeline/metrics.py`](../../../backend/src/koherent/pipeline/metrics.py)
computes `hit@k` and reciprocal rank (→ MRR) from marker matches, no LLM call
needed. The first 5 queries additionally run the full `ask` pipeline and are
scored by [`pipeline/judge.py`](../../../backend/src/koherent/pipeline/judge.py):
the judge is instructed to return **strict JSON** splitting the answer into
claims with `supported`/`unsupported` verdicts; parsing tolerates markdown
code fences (models add them unprompted) but is strict about JSON shape and
verdict vocabulary — anything else is counted as a `parse_error`, tracked
separately rather than silently coerced into a verdict.
[`evals/run_eval.py`](../../../backend/evals/run_eval.py) writes a committed
report artifact (`backend/samples/eval_report.{md,json}`; real NIM adapters
when `NVIDIA_API_KEY` is set, `FakeAIClient` otherwise with a disclosed "fake
mode" header in the report) and an offline sanity gate asserts `hit@5 >= 0.5`.

**[D-033] `/process`, `/report`, and the new class-scoped endpoints share one
authz module; a report is scoped to the caller's own notes.**
[`routes/access.py`](../../../backend/src/koherent/routes/access.py) centralizes
two checks used by every resource-scoped route: `load_lecture_for_student`
(404 if the lecture doesn't exist, 403 if it belongs to another class) and
`require_class_member` (403 if the URL's `class_id` isn't the caller's own).
`/lectures/{id}/process`, `/lectures/{id}/report`, `/lectures/{id}/summary`,
`/lectures/{id}/review`, `/classes/{id}/materials`, `/classes/{id}/ask`, and
`/classes/{id}/explain` all route through one of the two helpers.
`GET /lectures/{id}/report` additionally filters to
`Note.student_id == current.id` — the caller's own notes only, not the whole
class's.

---

## 3. What we rejected, and why

- **A separate `LLMClient` seam parallel to `AIClient`.** More moving parts and
  two things to inject where FastAPI DI already gives us one; `generate` joining
  the existing Protocol keeps "one client" true.
- **Sniffing MIME type for document uploads.** Browsers send `text/plain` or
  nothing useful for `.md`; the filename suffix is unambiguous and is what the
  user actually sees.
- **One chunker generalized to handle both time and word windows.** Would need
  a fake time axis bolted onto documents for no real benefit; two small,
  single-purpose chunkers (topic 07's `chunking.py`, this page's
  `text_chunking.py`) are easier to read and test in isolation.
- **Leaving retrieval queries embedded as `"passage"`.** The MVP shortcut noted
  in D-025; now that the assistant endpoints exist and are the main consumer
  of retrieval quality, closing the gap is worth the one-line adapter change.
- **Chunk-id-based golden answers.** Brittle — any re-chunking or re-embedding
  run invalidates the whole golden set. Marker substrings survive both.
- **A large general-purpose eval framework.** Disproportionate for a 14-query
  smoke check; a few hundred lines of pure functions (`metrics.py`, `judge.py`)
  are easier to read, trust, and extend than adopting a framework's opinions.
- **Silently coercing judge parse failures into a verdict.** Hides exactly the
  failure mode (a judge that didn't follow instructions) that's most useful to
  know about; counting `parse_error` explicitly surfaces it instead.
- **An unscoped `/report` (whole-class notes to any member).** A privacy leak —
  any student could read classmates' raw notes. Full-class visibility is a
  professor-only capability that doesn't exist yet (no professor
  role/authentication is built); scoping to the caller's own notes is the
  honest MVP boundary until that role ships.

---

## 4. In our code

| Thing | Where |
|-------|-------|
| The seam (`generate`, `embed_query` additions) | [`ai/base.py`](../../../backend/src/koherent/ai/base.py) |
| NIM chat adapter | [`ai/chat.py`](../../../backend/src/koherent/ai/chat.py) |
| Real composite (Riva + NIM embed + NIM chat) | [`ai/real.py`](../../../backend/src/koherent/ai/real.py) |
| Fake client's judge-parseable JSON path | [`ai/fake.py`](../../../backend/src/koherent/ai/fake.py) |
| Document text extraction | [`pipeline/extraction.py`](../../../backend/src/koherent/pipeline/extraction.py) |
| Word-count document chunking | [`pipeline/text_chunking.py`](../../../backend/src/koherent/pipeline/text_chunking.py) |
| Top-k cosine retrieval | [`pipeline/retrieval.py`](../../../backend/src/koherent/pipeline/retrieval.py) |
| Grounded prompt templates + context budget | [`pipeline/prompts.py`](../../../backend/src/koherent/pipeline/prompts.py) |
| LLM-judge groundedness scoring | [`pipeline/judge.py`](../../../backend/src/koherent/pipeline/judge.py) |
| Retrieval metrics (hit@k, MRR) | [`pipeline/metrics.py`](../../../backend/src/koherent/pipeline/metrics.py) |
| Materials ingestion endpoints | [`routes/materials.py`](../../../backend/src/koherent/routes/materials.py) |
| Grounded ask/explain endpoints | [`routes/assistant.py`](../../../backend/src/koherent/routes/assistant.py) |
| Summary/review endpoints | [`routes/study.py`](../../../backend/src/koherent/routes/study.py) |
| Shared authz helpers | [`routes/access.py`](../../../backend/src/koherent/routes/access.py) |
| Golden set + eval runner | [`evals/golden.json`](../../../backend/evals/golden.json), [`evals/run_eval.py`](../../../backend/evals/run_eval.py) |
| Committed eval report | [`backend/samples/eval_report.md`](../../../backend/samples/eval_report.md) |

---

## 5. Decision records

### D-029: Chat generation behind the same seam

- **Date:** 2026-07-08
- **Status:** Active
- **Context:** The assistant endpoints (ask/explain/summary/review) need LLM
  text generation, not just embeddings/transcription, and must stay testable
  offline like the rest of the seam.
- **Decision:** Add `generate(system_prompt, user_prompt) -> str` to the
  `AIClient` Protocol; `NIMChatClient` implements it over the OpenAI SDK
  against NIM's chat endpoint, model from `nim_chat_model` (default
  `meta/llama-3.3-70b-instruct`), temperature `0.2`. `FakeAIClient.generate`
  returns deterministic tagged text, or judge-parseable JSON when the system
  prompt says `"Return ONLY JSON"`.
- **Why:** One more capability behind the existing Protocol keeps
  ports-and-adapters intact; reusing the OpenAI-SDK-at-NVIDIA's-`base_url`
  pattern from `embeddings.py` keeps NVIDIA specifics contained per adapter. A
  low, fixed temperature favors grounded, low-variance answers over creative
  ones, appropriate for a study assistant that must not invent material.
- **Alternatives rejected:** A separate `LLMClient` seam (more moving parts,
  breaks the single-injected-client story); an exposed/configurable
  temperature (unneeded knob for a grounded-answer use case).

### D-030: Document ingestion & text chunking

- **Date:** 2026-07-08
- **Status:** Active
- **Context:** The assistant needs a corpus beyond lecture transcripts —
  uploaded course materials (`.txt`/`.md`/`.pdf`).
- **Decision:** `pipeline/extraction.py` dispatches by filename suffix (not
  MIME type); `.txt`/`.md` decode as UTF-8, `.pdf` via `pypdf`; unsupported →
  415, empty/corrupt/no-extractable-text → 422. `pipeline/text_chunking.py` is
  a new module, separate from the time-based `pipeline/chunking.py`:
  paragraph-aware ~250-word chunks with 50-word overlap when a paragraph must
  be split.
- **Why:** Documents have no timeline, so word-count windowing is the natural
  unit, and keeping it a separate module keeps each chunker single-purpose.
  Suffix dispatch is unambiguous and matches what users see; browser MIME
  types for `.md` are not reliable.
- **Alternatives rejected:** MIME-type sniffing (unreliable for `.md`); one
  chunker generalized over time and word windows (forces an artificial time
  axis onto documents); OCR for scanned PDFs (out of scope — rejected as
  empty rather than silently ingesting blank chunks).

### D-031: Query-typed retrieval

- **Date:** 2026-07-08
- **Status:** Active
- **Context:** `nv-embedqa-e5-v5` is an asymmetric embedding model with
  distinct query/passage encodings; [D-025](07-ai-pipeline.md#d-025-embeddings-via-nvidia-nim-nv-embedqa-e5-v5)
  flagged embedding everything as `"passage"` as a documented gap. The new
  ask/explain/summary/review endpoints all embed a live query against many
  stored passage vectors.
- **Decision:** Add `embed_query(text) -> vector` to the seam. `NIMEmbedder`
  calls NIM with `input_type="query"` for `embed_query`,
  `input_type="passage"` (unchanged default) for `embed`. `FakeAIClient`'s
  `embed_query` returns the same vector as `embed` (a symmetric fake).
  `pipeline/retrieval.py::top_k` does a Python-loop cosine scan, reusing
  `pipeline/alignment.py`'s `cosine` — the same no-pgvector-yet approach as
  [D-026](07-ai-pipeline.md#d-026-store-vectors-as-float-columns-cosine-in-python-no-pgvector).
- **Why:** Closes a real, previously-documented quality gap for the model's
  intended use. Keeping cosine in Python at class-corpus scale preserves the
  same "visible math, no extension" reasoning as D-026. Extends D-025/D-026
  rather than superseding them — same model, same storage, now used as
  designed.
- **Alternatives rejected:** Continuing to embed queries as `"passage"` (the
  closed MVP shortcut); adopting `pgvector` now (still premature at this
  scale).

### D-032: Eval design

- **Date:** 2026-07-08
- **Status:** Active
- **Context:** The retrieval + generation stack needs a repeatable,
  automatic way to check for regressions, without overclaiming benchmark-grade
  rigor a 14-query set over one small corpus can't support.
- **Decision:** A marker-based (substring, not chunk-id) 14-query golden set
  (`evals/golden.json`) over the committed econ material and sample lecture
  transcript; `pipeline/metrics.py` computes hit@k/MRR from marker matches.
  The first 5 queries also run the full `ask` pipeline and are judged by an
  LLM (`pipeline/judge.py`) with strict-JSON parsing and explicit
  `parse_error` accounting (not silently coerced). `evals/run_eval.py` writes
  a committed report (`backend/samples/eval_report.{md,json}`; real NIM when
  `NVIDIA_API_KEY` is set, disclosed fake mode otherwise); an offline sanity
  gate asserts `hit@5 >= 0.5`. Framed explicitly as smoke metrics, not
  benchmarks.
- **Why:** Marker matching survives re-chunking/re-embedding where chunk ids
  would not. hit@k/MRR are cheap, standard, and need no LLM call. Explicit
  parse-error accounting on the judge avoids hiding a failure mode inside a
  guessed verdict. Honest framing (smoke test, not benchmark) matches what 14
  queries over one corpus can actually support.
- **Alternatives rejected:** Chunk-id golden answers (brittle); a full eval
  framework (disproportionate); silently discarding or guessing on judge
  parse failures (hides the failure instead of measuring it).

### D-033: Report scoping / authz

- **Date:** 2026-07-08
- **Status:** Active
- **Context:** `/process`, `/report`, and the new materials/assistant
  endpoints all take a `class_id`/`lecture_id` from the URL; without a
  membership check a student could act on or read another class's data by
  guessing an id.
- **Decision:** A shared `routes/access.py` centralizes
  `load_lecture_for_student` (404 missing, 403 wrong class) and
  `require_class_member` (403 if the URL's class isn't the caller's own),
  used by every resource-scoped route (`process`, `report`, `summary`,
  `review`, `materials`, `ask`, `explain`). `GET /lectures/{id}/report` is
  additionally scoped to the caller's own notes (`Note.student_id ==
  current.id`), not the whole class's.
- **Why:** One shared module means every route enforces the same policy
  instead of each author reinventing (or forgetting) an ownership check.
  404-then-403 avoids leaking resource existence to non-members. Scoping the
  report to the caller's own notes is the honest MVP boundary — a full-class
  view is a professor-only capability that isn't built yet (no professor
  role/authentication exists), so returning classmates' notes to a student
  would be a privacy leak, not a feature.
- **Alternatives rejected:** An unscoped full-class report (privacy leak);
  building the professor role now to unlock it properly (larger scope than
  this task; deferred).
