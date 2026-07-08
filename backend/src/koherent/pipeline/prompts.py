"""Prompt construction for the assistant endpoints.

Pure string builders, kept out of route handlers so grounding rules are
testable and consistent: every generative endpoint speaks to the model
through these templates, and every answer is grounded in a numbered
context block whose entries the model must cite.
"""
from dataclasses import dataclass

from koherent.pipeline.retrieval import ScoredChunk

GROUNDED_SYSTEM_PROMPT = (
    "You are a study assistant for a university class. Answer ONLY from the "
    "numbered context excerpts provided by the user. If the context does not "
    'contain the answer, reply exactly: "Not covered in the course materials." '
    "Cite the excerpt numbers you used in square brackets, e.g. [1][3]. "
    "Be concise and factual; never invent material that is not in the context."
)

SUMMARY_SYSTEM_PROMPT = (
    "You are a study assistant. Produce a structured markdown summary of a "
    "lecture transcript with exactly these sections: '## Overview' (2-3 "
    "sentences), '## Key concepts' (bulleted term: one-line definition), and "
    "'## Section by section' (one bullet per transcript section, in order). "
    "Use only what the transcript says; do not add outside knowledge."
)

REVIEW_SYSTEM_PROMPT = (
    "You are a tutor writing personalized review prompts for one student. "
    "For each weak spot you are given (their note, and what the lecture "
    "actually said), write: what the lecture actually said (1-2 sentences), "
    "then 1-2 short check-yourself questions targeting the gap. Ground every "
    "item in the provided lecture excerpts only. Format as markdown with one "
    "'### Review N' section per weak spot."
)


def build_context_block(
    chunks: list[ScoredChunk], char_budget: int = 12000
) -> tuple[str, bool]:
    """Number chunks into a citable block, dropping whole chunks past the budget."""
    entries: list[str] = []
    used = 0
    truncated = False
    for i, chunk in enumerate(chunks, start=1):
        entry = f"[{i}] ({chunk.label}) {chunk.content}"
        separator = len("\n\n") if entries else 0
        if used + separator + len(entry) > char_budget:
            truncated = True
            break
        entries.append(entry)
        used += separator + len(entry)
    return "\n\n".join(entries), truncated


def build_ask_prompt(question: str, context_block: str) -> str:
    return f"Context excerpts:\n\n{context_block}\n\nQuestion: {question}"


def build_explain_prompt(concept: str, context_block: str) -> str:
    return (
        f"Context excerpts:\n\n{context_block}\n\n"
        f'Explain the concept "{concept}" using only the context above. '
        "Structure the explanation as: definition, intuition, example."
    )


def build_summary_prompt(lecture_title: str | None, chunk_texts: list[str]) -> str:
    title = lecture_title or "(untitled lecture)"
    sections = "\n\n".join(
        f"Section {i + 1}:\n{text}" for i, text in enumerate(chunk_texts)
    )
    return f"Lecture title: {title}\n\nTranscript sections, in order:\n\n{sections}"


@dataclass(frozen=True)
class ReviewItem:
    note_content: str
    matched_content: str | None
    similarity: float | None


def build_review_prompt(items: list[ReviewItem]) -> str:
    blocks: list[str] = []
    for i, item in enumerate(items, start=1):
        matched = item.matched_content or "(no matching lecture content was found)"
        similarity = f"{item.similarity:.2f}" if item.similarity is not None else "none"
        blocks.append(
            f"Weak spot {i} (match similarity: {similarity}):\n"
            f"Student's note: {item.note_content}\n"
            f"What the lecture said: {matched}"
        )
    return "The student's weak spots, from their own lecture notes:\n\n" + "\n\n".join(blocks)
