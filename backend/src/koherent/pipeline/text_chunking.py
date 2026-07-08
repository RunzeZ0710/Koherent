"""Chunk document text into embedding-sized pieces.

Separate from pipeline/chunking.py, which buckets ASR words by *time*;
documents have no timeline, so we window by word count instead. Paragraph
boundaries are respected where possible: short paragraphs merge into one
chunk, and a paragraph longer than the target is split into word windows
that carry `overlap_words` words forward so no idea is cut mid-context.
"""
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    index: int
    content: str


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def chunk_text(
    text: str, target_words: int = 250, overlap_words: int = 50
) -> list[TextChunk]:
    if overlap_words >= target_words:
        raise ValueError("overlap_words must be smaller than target_words")

    # Greedily pack whole paragraphs up to the target...
    groups: list[list[str]] = []
    current: list[str] = []
    for para in _paragraphs(text):
        para_words = para.split()
        if current and len(current) + len(para_words) > target_words:
            groups.append(current)
            current = []
        current.extend(para_words)
    if current:
        groups.append(current)

    # ...then split any group that alone exceeds the target, with overlap.
    chunks: list[TextChunk] = []
    for group in groups:
        start = 0
        while start < len(group):
            window = group[start : start + target_words]
            chunks.append(TextChunk(index=len(chunks), content=" ".join(window)))
            if start + target_words >= len(group):
                break
            start += target_words - overlap_words
    return chunks
