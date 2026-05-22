# AI-Native Notetaking — Project Plan

A high-agency project for an NVIDIA SWE internship application.

---

## Problem & Insight

Students take notes during lectures, but their notes often don't capture what the professor wanted them to capture — and the professor has no way to know what's landing and what isn't. There's no feedback loop. Office hours surface individual confusion, but **systematic class-wide misconceptions are invisible** unless a prof grades every set of notes by hand.

## The Product

An AI-native notetaking app that:
- Lets students take notes in-app during lecture
- Records lecture audio (one student per session)
- Compares student notes against the lecture as ground truth
- Gives each student personalized feedback on what they missed
- Gives the professor an aggregated dashboard showing class-wide patterns — especially **clusters of shared misconceptions** ("where the class went off the rails together")

The off-the-rails clustering is the novel insight: it's not "did students get it right," it's "did they get it wrong in the same way" — surfacing systematic teaching gaps that no other tool reveals.

---

## MVP Scope

### In Scope (3-4 weeks)
- Web app (no native mobile)
- Single class, 10-30 students
- Typed notes only
- One student per lecture records audio in-app
- Post-lecture processing (not real-time)
- Per-student feedback report after each lecture
- Aggregated professor dashboard after each lecture

### Out of Scope (V2+)
- Handwriting OCR
- Real-time during-lecture analysis
- Multi-class / multi-professor management
- LMS integration
- Native mobile apps
- Slide ingestion

---

## User Flows

### Student
1. Join class with a code, enter name
2. Take typed notes in-app during lecture (auto-timestamped as they type)
3. One designated student hits "record lecture"; audio uploads on stop
4. ~2-5 minutes after lecture ends, gets a personal report:
   - Concepts captured (8/10)
   - Notes flagged as potentially wrong, with corrections sourced from the lecture
   - Suggested study items

### Professor
1. **One-time setup:** create class, share join code with students, optionally upload syllabus or key concepts list
2. **After each lecture:** dashboard email or in-app notification
3. **Dashboard shows:**
   - **What landed** — concepts captured by >80% of class
   - **What didn't** — concepts captured by <30%
   - **Off the rails** — clusters of similar misconceptions: "9 students wrote X causes Y, but you said Y causes X"
   - **Outliers** — individual students who diverged from the rest (potential office hours candidates)
4. Each insight expandable to anonymized note excerpts

---

## The Killer Feature: Off-the-Rails Detection

Mechanism:

1. Extract claim-level statements from each student's notes (LLM)
2. Embed each claim
3. Compare to ground-truth transcript chunks via cosine similarity
4. Claims with low similarity to ground truth → flagged as "potentially wrong"
5. Cluster flagged claims across students by embedding similarity
6. Any cluster with N+ members → "the class went off the rails together"
7. Summary to prof highlights the cluster with sample misconceptions

This is also where the NVIDIA stack earns its keep: real GPU pipeline (batch embedding generation, similarity search against full transcript, clustering), not a single LLM call.

---

## Technical Architecture

### V1 — Hosted (ship fast, prove the loop)

```
Mac (dev) → Next.js frontend → Python/FastAPI backend → NVIDIA NIM API endpoints
                                                       → Postgres (notes, transcripts, results)
```

Components:
| Layer | Choice |
|-------|--------|
| Frontend | Next.js |
| Backend | Python (FastAPI) |
| Database | Postgres |
| ASR | Nemotron Speech or Riva (via NIM API) |
| Embeddings | `nvidia/nv-embedqa-e5-v5` (via NIM API) |
| LLM | `meta/llama-3.1-70b-instruct` (via NIM API) |
| Clustering | hdbscan or sklearn (CPU-side) |
| Storage | Local disk or S3 for audio files |

Cost: $0 (free tier on NIM API, ~40 RPM rate limit)

### V2 — Self-Hosted (the interview story)

Same code. Change `base_url` to point at locally-running NIM container.

```
Web app → Backend → NIM container running on:
                    - Rented GPU (Brev/Lambda/RunPod, $0.50-1.50/hr) for benchmarking
                    - OR Jetson Orin Nano ($249) for edge deployment demo
                    - OR RTX 4090 workstation if you have access
```

Optimizations to demo:
- TensorRT-LLM compilation of the LLM
- INT4/INT8 quantization for Jetson memory budget
- Batched inference for class-wide processing

Cost to benchmark: a few dollars for a rental session, or $249 one-time for a Jetson.

---

## Privacy & The V1→V2 Story

### V1 (development, classmates as test users)
- Hosted NIM endpoints are fine because:
  - Users are informed-consent classmates, not institutional data subjects
  - You're a side project, not an institutional agent (FERPA doesn't apply at this scale)
- **Required**: explicit "your notes will be processed by NVIDIA's hosted inference API" consent at signup
- **Recommended**: strip names before sending to API (use `note_id` references; keep names in your own DB)

### V2 (production-ready, the pitch)
- Fully self-hosted on school-controlled hardware
- Data never leaves the device
- Designed to run on:
  - A single $249 Jetson Orin Nano (8GB memory, INT4-quantized 4B model)
  - Or a $2k Jetson Orin AGX (64GB, larger models)
  - Or a $1600 RTX 4090 workstation under a professor's desk

**Don't claim self-hosting capability you haven't shipped.** The migration must actually be demoed before being part of the pitch.

---

## Deployment Economics

| Option | Hardware Cost | Use Case |
|--------|---------------|----------|
| Jetson Orin Nano | ~$249 one-time | Single classroom edge, air-gapped |
| Jetson Orin AGX | ~$2,000 one-time | Department-wide, larger models |
| RTX 4090 workstation | ~$1,600 + PC | Department server, fastest |
| Rented dedicated GPU | $0.50-1.50/hr | Pilot deployments, dev/test |

NIM containers themselves are **free** for development under the NVIDIA Developer Program (up to 2 nodes / 16 GPUs). The only cost is the hardware.

The pitch: "deployable to a small school for the price of one $249 device per classroom, no per-seat licensing, free NIM software."

---

## Build Plan (Week-by-Week)

### Week 1: Foundation
- [ ] Sign up for NVIDIA Developer Program at build.nvidia.com
- [ ] Get NIM API key, test chat/embedding/ASR endpoints
- [ ] Scaffold Next.js + FastAPI + Postgres
- [ ] Build auth, class creation, join codes
- [ ] Build typed note-taking UI (auto-timestamped)
- [ ] Build audio upload + storage
- [ ] **Goal:** upload a 5-min audio clip and typed notes, persist to DB

### Week 2: The Pipeline
- [ ] Transcription pipeline (Nemotron Speech or Riva via NIM)
- [ ] Transcript chunking (~30s fixed chunks initially)
- [ ] Embedding pipeline (notes and transcript chunks)
- [ ] Note-to-transcript alignment via cosine similarity
- [ ] LLM-based claim extraction from notes
- [ ] LLM-as-judge: "did this note capture this concept correctly?"
- [ ] Per-student feedback report generation
- [ ] **Goal:** one student's full flow works end-to-end on real data

### Week 3: The Dashboard
- [ ] Cross-student aggregation logic
- [ ] Misconception clustering (the off-the-rails detector)
- [ ] Professor dashboard UI
- [ ] Anonymized note excerpt views
- [ ] Email/notification when dashboard is ready
- [ ] **Goal:** dashboard shows real data from a real lecture with 5+ test students

### Week 4: Dogfood + Migration
- [ ] Run with 10-30 classmates in your own class for a real lecture
- [ ] Fix what breaks
- [ ] Spin up self-hosted NIM container on a rented GPU (Brev/Lambda)
- [ ] Benchmark hosted vs self-hosted: latency, cost-per-lecture, throughput
- [ ] Write up deployment story / README / one-pager
- [ ] (Stretch) Run on a Jetson if you bought one

### Parallel Track (start Week 1)
- [ ] Identify one friendly TA or professor who'll opt in
- [ ] Get classmate buy-in for testing
- [ ] Join NVIDIA Developer forums / Discord for support

---

## Day 1 Setup Checklist

1. Sign up at https://build.nvidia.com → grab API key (prefixed `nvapi-`)
2. Install Python deps: `pip install openai fastapi uvicorn psycopg2-binary`
3. Test the NIM API works from your Mac:

```python
from openai import OpenAI

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key="nvapi-..."
)

r = client.chat.completions.create(
    model="meta/llama-3.1-70b-instruct",
    messages=[{"role": "user", "content": "Hello, are you reachable?"}]
)
print(r.choices[0].message.content)
```

4. Test embeddings:

```python
e = client.embeddings.create(
    model="nvidia/nv-embedqa-e5-v5",
    input="The marginal cost equals the change in total cost over change in quantity."
)
print(len(e.data[0].embedding))
```

5. Test ASR with a 30-second audio sample (consult build.nvidia.com for the specific Nemotron Speech / Riva endpoint format — speech APIs differ slightly from chat).

---

## Key Decisions to Make

1. **Anonymization in prof dashboard** — Default: fully anonymous; show names only when prof drills into a specific outlier and opts in.
2. **Transcript chunking strategy** — Start with fixed 30s chunks. If alignment is too noisy, refine to topic-shift detection.
3. **"Off the rails" threshold** — Start with 3+ students with similar misconceptions; make tunable.
4. **Model sizes** — V1: Llama 3.1 70B hosted. V2: Llama 3.1 8B or smaller, quantized to fit Jetson memory budget.
5. **Recording consent flow** — One student designates themselves the recorder; visible indicator in-app when recording is active.

---

## NVIDIA Stack Mapping

| Component | NVIDIA Tech | Justification |
|-----------|-------------|---------------|
| ASR | Nemotron Speech / Riva | GPU-optimized speech recognition |
| Embeddings | NeMo Retriever (`nv-embedqa-e5-v5`) | Fast batched embedding generation |
| LLM hosting | NIM containers | Same code hosted or self-hosted |
| Inference optimization | TensorRT-LLM | Real latency/throughput story |
| Edge deployment | Jetson + JetPack | $249 air-gapped FERPA-compliant option |
| Safety | NeMo Guardrails (optional) | Prevent LLM judge hallucinations |

---

## Interview Talking Points

1. **The product loop closes a real gap.** Professors literally cannot get this signal any other way.
2. **The off-the-rails clustering is a novel application of embeddings.** Not just "did they get it right" but "did they get it wrong in the same way."
3. **The migration story is the SWE narrative.** Shipped V1 on hosted endpoints to validate fast. Migrated to self-hosted NIM container for the privacy story. Benchmarked the move (latency before/after, cost-per-lecture at scale).
4. **Deployment economics are real.** $249 per classroom Jetson, free NIM software, no per-seat fees. The unit economics work because of NVIDIA's pricing structure.
5. **Honest tradeoffs.** "I didn't ship handwriting, real-time, or multi-class because [reasons]. Here's what I'd build next and why."

---

## Risks & Open Questions

- **Note-to-lecture alignment is harder than it sounds.** Soft matching across embeddings, not string matching. May need iteration.
- **"Captured correctly" is fuzzy.** LLM-as-judge needs guardrails or it'll hallucinate concepts that weren't in the lecture.
- **Getting one professor to opt in.** Longest-lead-time item. Start asking week 1.
- **Rate limits on free tier (40 RPM).** A class of 30 students × 20 LLM calls each = 600 calls. Plan to queue with backoff. This is actually a good engineering story to tell.
- **ASR quality on lecture audio.** Will fail on heavy accents, bad mics, or multilingual classes. Test early.
- **What if Nemotron Speech / Riva isn't precise enough?** Whisper-large via NIM as fallback.

---

## What Success Looks Like by Interview Day

- A working demo URL (or local demo) where you can show:
  - Student taking notes during a lecture
  - Lecture being processed
  - Student getting personalized feedback
  - Professor dashboard with a real "off the rails" cluster from real classmate notes
- A README with the architecture diagram and the V1→V2 migration story
- Benchmark numbers from running self-hosted on a rented GPU
- (Bonus) A Jetson running the inference path locally, that you can demo physically
- A 90-second pitch you can deliver cold: "students take notes, professor gets the dashboard showing class-wide comprehension gaps, runs on a $249 NVIDIA device per classroom, here's how I built it"
