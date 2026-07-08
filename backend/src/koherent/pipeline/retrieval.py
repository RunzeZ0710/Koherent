"""Top-k retrieval over embedded chunks.

Pure and DB-free, like alignment.py: callers build Candidates from whatever
rows they queried (material chunks, transcript chunks) and get back the k
best matches by cosine similarity. Python-loop scan is deliberate — a class's
corpus is thousands of chunks at most (pgvector is the documented scale path,
wiki D-026).
"""
import uuid
from dataclasses import dataclass

from koherent.pipeline.alignment import cosine


@dataclass(frozen=True)
class Candidate:
    source: str  # "material" | "transcript"
    ref_id: uuid.UUID
    label: str
    content: str
    vector: list[float]


@dataclass(frozen=True)
class ScoredChunk:
    source: str
    ref_id: uuid.UUID
    label: str
    content: str
    score: float


def top_k(
    query_vector: list[float], candidates: list[Candidate], k: int = 5
) -> list[ScoredChunk]:
    scored = [
        ScoredChunk(
            source=c.source,
            ref_id=c.ref_id,
            label=c.label,
            content=c.content,
            score=cosine(query_vector, c.vector),
        )
        for c in candidates
    ]
    scored.sort(key=lambda s: -s.score)  # sort is stable: ties keep candidate order
    return scored[:k]
