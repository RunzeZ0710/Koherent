# Koherent

**Koherent links messy, free-typed lecture notes to the authoritative transcript they refer to, scores each link, and flags notes that match nothing the lecture actually said.**

Students type notes during a lecture; the lecture audio is transcribed; the system
then resolves every note to the specific span of the transcript it corresponds to,
attaches a confidence score, and surfaces the notes that don't resolve to anything —
the seed of detecting where a class has gone off the rails together.

It's a small, end-to-end **data-integration pipeline**: two streams of untrusted
human input (audio + free text) become linked, scored, queryable relationships
against a ground-truth source.

---

## The pipeline as a data problem

This is record linkage against a ground-truth source, not a single LLM call:

```
audio ──Riva ASR──▶ transcript ──chunk(30s)──▶ chunks ──┐
                                                         ├─embed─▶ vectors ─cosine─▶ note→chunk links + score ─▶ anomaly flag
student notes ───────────────────────────────────────────┘
        (all AI behind one AIClient seam: FakeAIClient offline · NVIDIA Riva + NIM for real)
```

| Stage | What it does | Where |
|-------|--------------|-------|
| Transcribe | lecture audio → text + per-word timestamps | [`ai/riva.py`](backend/src/koherent/ai/riva.py) |
| Chunk | transcript → ~30s timestamped spans | [`pipeline/chunking.py`](backend/src/koherent/pipeline/chunking.py) |
| Embed | chunks + notes → vectors (`nv-embedqa-e5-v5`) | [`ai/embeddings.py`](backend/src/koherent/ai/embeddings.py) |
| Link | each note → best-matching chunk by cosine similarity | [`pipeline/alignment.py`](backend/src/koherent/pipeline/alignment.py) |
| Flag | best similarity below threshold → anomaly | [`pipeline/report.py`](backend/src/koherent/pipeline/report.py) |
| Orchestrate | run + persist all of the above, idempotently | [`pipeline/process.py`](backend/src/koherent/pipeline/process.py) |

## The assistant layer: retrieval-augmented Q&A over the class corpus

On top of the lecture pipeline sits a second, document-shaped corpus and a
generation step, so students can ask questions instead of only getting a
per-note report:

```
uploaded .txt/.md/.pdf ──extract+chunk(~250w)──▶ material chunks ──┐
                                                                    ├─embed(passage)─▶ vectors ──┐
lecture transcript chunks ─────────────────────────────────────────┘                             │
                                                                                                   ▼
student question ──embed(query)──▶ top-k cosine over class vectors ──▶ numbered context block ──▶ generate() ──▶ answer + citations
```

| Stage | What it does | Where |
|-------|--------------|-------|
| Ingest | upload → extract text (.txt/.md/.pdf) → ~250-word paragraph-aware chunks | [`pipeline/extraction.py`](backend/src/koherent/pipeline/extraction.py), [`pipeline/text_chunking.py`](backend/src/koherent/pipeline/text_chunking.py) |
| Retrieve | embed the question as a query, rank every material + transcript chunk in the class by cosine, take top-5 | [`pipeline/retrieval.py`](backend/src/koherent/pipeline/retrieval.py) |
| Generate | assemble a numbered, char-budgeted context block; generate an answer that must cite it | [`pipeline/prompts.py`](backend/src/koherent/pipeline/prompts.py), [`ai/chat.py`](backend/src/koherent/ai/chat.py) |

| Endpoint | What it does |
|----------|--------------|
| `POST /classes/{id}/materials` | upload a course document; extracted, chunked, embedded, stored |
| `GET /classes/{id}/materials` | list a class's uploaded materials |
| `POST /classes/{id}/ask` | grounded Q&A over the class's materials + transcripts, with citations |
| `POST /classes/{id}/explain` | grounded concept explanation, same retrieval + citation path |
| `POST` / `GET /lectures/{id}/summary` | structured lecture summary (cached; `POST` regenerates) |
| `POST /lectures/{id}/review` | personalized review prompts sourced from the caller's own anomalous/lowest-similarity notes |

The retrieval-backed endpoints (`ask`, `explain`) return `citations` (the
exact chunks the model saw) and a `truncated` flag (whether the context was
cut off by the 12,000-char budget) — every answer is traceable back to the
class's actual materials or transcripts, not the model's own recall.
`summary` and `review` skip retrieval by design: `summary` is generated from
the lecture's own transcript chunks in order, and `review` from the calling
student's own weak notes and their matched transcript spans.

## Does it actually work? The eval harness

[`backend/evals/`](backend/evals/) is a small, honest eval harness, not a
benchmark claim: a 14-query golden set (7 over a committed econ course-material
doc, 7 over the committed sample lecture transcript) scored by `hit@k`/MRR
(marker-substring match, stable across re-chunking), plus an LLM-as-judge pass
that scores the first 5 answers' claims as supported/unsupported against the
retrieved context (parse failures counted explicitly, not guessed at). Run it
with `cd backend && uv run python evals/run_eval.py` — it writes
[`backend/samples/eval_report.md`](backend/samples/eval_report.md) (and a
`.json` twin), using real NVIDIA adapters when `NVIDIA_API_KEY` is set and the
deterministic `FakeAIClient` otherwise (disclosed in the report header either
way). An offline sanity check asserts `hit@5 >= 0.5`.

## See it without running anything

[`samples/sample_report.md`](samples/sample_report.md) is generated by the real
pipeline (NVIDIA `nv-embedqa-e5-v5`) on a real, messy ASR transcript:

| Student note | Similarity | Anomaly |
| --- | ---: | :---: |
| small businesses lose roughly 3.5 to 4 percent … to credit card fees | 0.6666 | no |
| credit card processing fees are often passed on to the consumer | 0.5446 | no |
| small businesses **love** using credit cards *(lecture said "hate")* | 0.5908 | no |
| the mitochondria is the powerhouse of the cell *(off-topic)* | 0.3741 | ⚠️ yes |

This is honest about what embedding retrieval does and doesn't catch: the
**off-topic** note is flagged, but the **on-topic-but-wrong** note ("love" vs the
lecture's "hate") links with high similarity — embeddings match *topic*, not
*truth*. Catching factual errors per-note is the job of an LLM-as-judge layer,
which exists today only inside the eval harness (scoring assistant-answer
groundedness, see below) — surfacing a correctness verdict back to the student
on their own notes is designed but not yet built (see "Built vs. designed-next"
below).

## Run it yourself (offline, no API key)

The whole pipeline runs against a deterministic `FakeAIClient` — no network, no
NVIDIA key — so the test suite exercises every stage end-to-end.

```bash
docker compose up -d db                                    # Postgres on :5433
cd backend && uv sync --extra dev
docker compose exec db psql -U koherent -d koherent -c 'CREATE DATABASE koherent_test;'  # one-time
uv run alembic upgrade head
uv run pytest                                              # whole pipeline, green, no network
```

Regenerate the sample report (uses real NVIDIA embeddings if `NVIDIA_API_KEY` is
set, otherwise the fake embedder with a disclosed header):

```bash
cd backend && uv run python scripts/run_sample_report.py
```

To run the app (capture UI), see [Local development](#local-development) below.

## The seam: one interface, two backends

Every AI call hides behind a single Protocol — [`ai/base.py`](backend/src/koherent/ai/base.py):

```python
class AIClient(Protocol):
    def transcribe(self, audio_path: str) -> Transcription: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
    def generate(self, system_prompt: str, user_prompt: str) -> str: ...
```

The pipeline depends only on this shape. `FakeAIClient` implements it for
deterministic offline tests; `RealAIClient` composes NVIDIA Riva (ASR) + NIM
embeddings (`nv-embedqa-e5-v5`, asymmetric query/passage encoding via
`embed_query`/`embed`) + NIM chat (`generate`, default
`meta/llama-3.3-70b-instruct`) for real runs. Swapping backends changes one
injected dependency and touches no pipeline or route code — the
ports-and-adapters pattern, and the basis for a later hosted→self-hosted
migration.

## Built vs. designed-next

**Built and tested (this branch):**
- Capture: join-by-code, timestamped note autosave, in-browser audio upload
- Transcription (NVIDIA Riva), 30s chunking, embedding (NVIDIA NIM)
- Note→chunk linking with cosine similarity + per-note anomaly flagging
- `POST /lectures/{id}/process` (idempotent) and `GET /lectures/{id}/report`
  (scoped to the caller's own notes; class-membership guarded, 403 cross-class)
- A committed real-data sample report
- Course-material ingestion (`.txt`/`.md`/`.pdf`) with paragraph-aware chunking
- Query-typed retrieval (top-k cosine over materials + transcripts) and
  grounded generation: `ask` + `explain` (RAG with citations), `summary`
  (from transcript chunks), `review` (from the caller's weak notes)
- Chat generation behind the same `AIClient` seam (NVIDIA NIM, OpenAI SDK
  transport)
- An eval harness (retrieval hit@k/MRR + LLM-judge groundedness) with a
  committed report artifact

**Designed, not yet built** (specs in [`docs/superpowers/specs/`](docs/superpowers/specs/)):
- **Cross-student misconception *clustering*** — the "off the rails" professor
  dashboard that groups *shared* anomalies across a class. This is the headline
  feature and it is explicitly not implemented yet.
- **Per-note LLM-as-judge correctness feedback** — claim extraction + a
  correctness verdict shown back to the student, to catch on-topic-but-wrong
  notes, which embedding similarity alone cannot. (An LLM-judge now exists in
  the eval harness above, but it scores *assistant-answer groundedness for
  regression-testing*, not individual student notes — the note-level feedback
  feature itself is still unbuilt.)
- **Professor role** — no professor authentication or account type exists yet;
  today every caller is a student, and `/report` is deliberately scoped to the
  caller's own notes because a full-class view has no authorized role to gate
  it behind.
- **Background job processing** — lecture and material processing are
  synchronous and inline (deliberate for now, see wiki D-028); a queue is a
  planned upgrade if real-workload latency demands it, not a correction.

---

## Local development

### Prerequisites
- Docker Desktop
- Python 3.11+ via [`uv`](https://docs.astral.sh/uv/)
- Node 20+ via `pnpm`

> **Port note:** Postgres runs on host port **5433** (not 5432) to coexist with
> another local Postgres. The container still listens on 5432 internally.

### One-time setup

```bash
docker compose up -d db
cd backend && uv sync --extra dev
cp .env.example .env
docker compose exec db psql -U koherent -d koherent -c 'CREATE DATABASE koherent_test;'
uv run alembic upgrade head
cd ../frontend && pnpm install && cp .env.local.example .env.local
```

### Run (three terminals)

```bash
docker compose up -d db                                          # 1. Postgres
cd backend && uv run uvicorn koherent.main:app --reload --port 8000   # 2. Backend
cd frontend && pnpm dev                                          # 3. Frontend
```

Open http://localhost:3002.

### Tests

```bash
cd backend && uv run pytest
```

## Repository layout

- `backend/` — FastAPI + SQLAlchemy + Alembic; the `ai/` seam, `pipeline/` stages, and `evals/` harness
- `frontend/` — Next.js (App Router, TypeScript, Tailwind) capture UI
- `samples/` — committed real-data pipeline sample report (`sample_report.{md,json}`)
- `backend/samples/` — committed eval report artifact (`eval_report.{md,json}`), written by `evals/run_eval.py`
- `docs/wiki/` — the engineering decision log (D-001…D-033), doubling as a from-scratch SWE learning resource
- `docs/superpowers/` — design specs and TDD implementation plans
- `project_plan.md` — the full product vision (including the deferred dashboard)
