# Koherent — Portfolio MVP (design)

**Date:** 2026-06-29
**Status:** Approved (design); implementation plan to follow
**Driver:** A few-days sprint to make the repo *GitHub-worthy* for an internship
application (Palantir), framed around **data integration / ontology**, not the
NVIDIA edge-deployment pitch.

This spec sits on top of the existing
[`2026-05-30-week-2a-retrieval-pipeline-design.md`](2026-05-30-week-2a-retrieval-pipeline-design.md).
It does not redesign the pipeline internals (data model, the AIClient seam,
chunking, alignment math) — those are already specified and partly built. It
defines the **smallest finished, runnable, well-narrated slice** that turns the
in-progress branch into something worth linking on a résumé.

---

## Why this scope

The repo is ~40% through a 4-week plan. The capture half (Next.js + FastAPI +
Postgres, join codes, note autosave, audio upload) is **done and tested**. Real
ASR via NVIDIA Riva is **done and proven on a real lecture** (cached output in
`scratch_test2.json`). But the *centerpiece* — note→transcript alignment — is
stubbed (`cosine`/`align` are `NotImplementedError`; `embeddings.py` is an empty
placeholder), and there is no orchestrator, no endpoint, no reader-facing
narrative.

For a portfolio repo, the failure mode is a half-built centerpiece and a README
that reads like internal notes. The gap to "finished slice" is small and
well-defined, so we close it rather than start anything new.

**The genuinely novel feature — cross-student misconception *clustering* ("off
the rails") — is explicitly NOT in this MVP.** It is the Week 3 dashboard. We
ship the single-student linking + per-note anomaly flagging slice, and describe
the clustering as designed-next (the spec already exists). Honesty about this is
part of the pitch.

---

## The Palantir framing

The pipeline is presented as **record linkage against a ground-truth source**:
messy, free-typed human notes are resolved to the specific span of an
authoritative transcript they refer to, with a confidence score, and inputs that
resolve to *nothing* are surfaced as anomalies. That is a data-integration /
ontology problem (raw input → entities → linked, scored relationships → derived
signal), which is the language the README will speak.

---

## What we build (the slice)

Four deliverables, in dependency order. Pipeline internals follow the Week 2A
spec; only the *new or changed* surface is described here.

### 1. Make the pipeline run uniformly offline (resolve the seam mismatch)

The `AIClient.transcribe` seam currently returns `str`, but `chunking.py`
consumes `list[TranscriptWord]` and `riva.py` already returns the richer
`Transcription` (text + per-word ms timestamps). Resolve in favor of the richer
type:

- `AIClient.transcribe(audio_path) -> Transcription` (update the Protocol).
- `FakeAIClient.transcribe` returns a `Transcription` with **synthesized**
  per-word timestamps (e.g. fixed cadence per word) so chunking runs identically
  on fake and real data — no network needed for the whole pipeline.

### 2. Finish the centerpiece

- Implement `cosine()` and `align()` in `pipeline/alignment.py`; the 10 existing
  TDD tests (`tests/test_alignment.py`) go green.
- Replace the placeholder `ai/embeddings.py` with a real NIM embedder
  (`nvidia/nv-embedqa-e5-v5` via the OpenAI-compatible endpoint
  `https://integrate.api.nvidia.com/v1`), behind the same seam. Mirror the
  pattern in `riva.py`: all NVIDIA specifics contained in the adapter.

### 3. Orchestrator + endpoints

- `pipeline/process.py` — ties the 4 stages together (transcribe → chunk → embed
  chunks + notes → align), persists `Transcript`, `TranscriptChunk`,
  `Note.embedding`, `NoteAlignment`. Idempotent reprocess (clears this lecture's
  derived rows, rebuilds).
- `POST /lectures/{id}/process` — runs the pipeline synchronously (the fake
  client is instant; real runs are short). Integration-tested against
  `FakeAIClient` via FastAPI dependency override (add a `get_ai_client` provider
  in `deps.py`, defaulting to the real composite, overridden to fake in tests).
- `GET /lectures/{id}/report` — the reader-facing artifact: per note, the linked
  transcript-chunk text, the timestamp span, the similarity score, and an
  `anomaly` flag (`similarity < threshold`). Threshold is configurable in
  `config.py` (start at a hand-tuned default).

### 4. The "wow": one committed real-data sample

A small script (`scripts/run_sample_report.py` or similar) runs the full pipeline
once through the **real** embedder on the real cached transcript + a handful of
realistic student notes (some good, one deliberately wrong, e.g. "marginal cost
equals marginal revenue is where you *minimize* profit"), and writes the report
to a committed artifact (`samples/sample_report.json` + a rendered
`samples/sample_report.md`). This is the thing a reader sees without running
anything. If the embedding key is unavailable, fall back to the fake embedder for
the committed sample and say so in the artifact header — never fabricate.

---

## The narrative work (half the value)

- **README rewrite** — the data-integration framing above; an architecture
  diagram (capture → transcribe → chunk → embed → link/score → anomaly flag);
  a "run it in 60 seconds" section (offline, via the fake client, no key needed);
  the committed sample report linked inline; and an explicit **Built vs.
  Designed-Next** section that names the deferred clustering dashboard.
- **Wiki update** — record the new decisions (seam return-type change, real
  embedder, anomaly threshold, sample-artifact approach) in `docs/wiki/` under the
  existing D-0xx framework.
- **Repo hygiene** — remove the `scratch_*.py` / `spike_asr.py` / `scratch_*.json`
  from the repo root (move to a gitignored `backend/scratch/` or delete; keep the
  one real cached transcript as a test fixture if useful). Commit the in-progress
  Week 2A work cleanly. A portfolio repo's root should read as intentional.

---

## Done bar (acceptance)

1. `tests/test_alignment.py` (10) and `tests/test_chunking.py` green; full
   backend suite green.
2. `POST /lectures/{id}/process` runs end-to-end on a seeded lecture offline (fake
   client), with an integration test asserting transcript, chunks (embedded), note
   embeddings, and one `NoteAlignment` per note persisted with sane values.
3. `GET /lectures/{id}/report` returns the per-note linked/scored/flagged report;
   tested.
4. `samples/sample_report.{json,md}` committed, generated from a real run
   (or fake with an honest header), showing at least one anomaly-flagged note.
5. README rewritten with diagram, 60-second offline run, sample linked, and the
   Built-vs-Designed-Next section.
6. Repo root cleaned of scratch/spike files; Week 2A work committed.

Out of scope: the cross-student clustering dashboard, the LLM claim-extraction /
LLM-as-judge feedback layer (Week 2B/3), any new frontend UI (the report is an
API + committed artifact; an in-app view is a stretch only if time remains).

---

## Risks / notes

- **Embedding key availability.** The real embedder is the one external
  dependency. If the NIM embedding endpoint isn't reachable with the available
  key, the slice still ships fully (offline fake path is the tested default); only
  the *real-data* sample degrades to fake, disclosed in the artifact.
- **Anomaly threshold is hand-tuned, not learned.** That's fine and honest at this
  scale; the README frames it as a tunable starting point, the same way the Week
  2A spec frames fixed 30s chunking.
- **Alignment realism.** With the fake embedder, alignments are deterministic but
  not semantically meaningful; the committed real-data sample is what demonstrates
  real-world quality. Both facts are stated plainly.
