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

    transcript_path = root / "tests" / "fixtures" / "sample_transcript.json"
    transcript_data = json.loads(transcript_path.read_text())
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
        "chat_model": "fake" if isinstance(ai, FakeAIClient) else settings.nim_chat_model,
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
    else:
        lines += [
            "> Real mode: embeddings `nvidia/nv-embedqa-e5-v5`; answers and judge "
            f"generated by `{results['chat_model']}`.",
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
