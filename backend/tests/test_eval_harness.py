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
