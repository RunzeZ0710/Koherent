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
