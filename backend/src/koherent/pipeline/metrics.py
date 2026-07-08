"""Retrieval metrics for the eval harness.

Golden queries carry a `marker` — a substring that must appear in a
retrieved chunk for it to count as the right chunk. Marker matching (not
chunk ids) keeps the golden set stable across re-chunking and re-embedding.
"""


def hit_at_k(ranked_contents: list[str], marker: str, k: int) -> bool:
    needle = marker.lower()
    return any(needle in content.lower() for content in ranked_contents[:k])


def reciprocal_rank(ranked_contents: list[str], marker: str) -> float:
    needle = marker.lower()
    for i, content in enumerate(ranked_contents):
        if needle in content.lower():
            return 1 / (i + 1)
    return 0.0
