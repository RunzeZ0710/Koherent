"""Stage 4 of the pipeline: align each note to the transcript chunk it best matches.

Pure and index-based: callers pass note vectors and chunk vectors (already embedded
elsewhere), and get back, for each note, the index of its best-matching chunk plus
the cosine similarity of that match. The orchestrator maps these indices back to
database IDs. Keeping this module free of DB and embedding concerns is exactly what
makes it trivial to test with hand-made vectors.
"""
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class AlignmentResult:
    """One note's best match: which chunk it aligned to, and how strong the match is."""

    note_index: int
    chunk_index: int
    similarity: float


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two vectors: dot(a, b) / (|a| * |b|).

    Returns a value in [-1, 1] — 1 = same direction, 0 = unrelated, -1 = opposite.
    A zero-length vector has no direction, so define its similarity as 0.0 (this
    also avoids dividing by zero).
    """
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(y * y for y in b))
    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0
    return dot / (mag_a * mag_b)


def align(
    note_vectors: list[list[float]],
    chunk_vectors: list[list[float]],
) -> list[AlignmentResult]:
    """For each note, find the chunk with the highest cosine similarity (argmax).

    Returns one AlignmentResult per note, in note order. With no chunks to match
    against, returns an empty list. On a tie, the earliest chunk wins.
    """
    results: list[AlignmentResult] = []
    for note_index, note_vec in enumerate(note_vectors):
        best_index = -1
        best_similarity = 0.0
        for chunk_index, chunk_vec in enumerate(chunk_vectors):
            similarity = cosine(note_vec, chunk_vec)
            # strict `>` so the EARLIEST chunk wins on a tie
            if best_index == -1 or similarity > best_similarity:
                best_index = chunk_index
                best_similarity = similarity
        if best_index == -1:
            continue  # no chunks to match against
        results.append(
            AlignmentResult(
                note_index=note_index,
                chunk_index=best_index,
                similarity=best_similarity,
            )
        )
    return results
