import uuid

from koherent.pipeline.prompts import (
    GROUNDED_SYSTEM_PROMPT,
    ReviewItem,
    build_ask_prompt,
    build_context_block,
    build_explain_prompt,
    build_review_prompt,
    build_summary_prompt,
)
from koherent.pipeline.retrieval import ScoredChunk


def _chunk(content: str, label: str = "econ_notes.md") -> ScoredChunk:
    return ScoredChunk(
        source="material", ref_id=uuid.uuid4(), label=label, content=content, score=0.9
    )


def test_context_block_numbers_and_labels_chunks():
    block, truncated = build_context_block([_chunk("alpha"), _chunk("beta", label="lecture:L1")])
    assert "[1] (econ_notes.md) alpha" in block
    assert "[2] (lecture:L1) beta" in block
    assert truncated is False


def test_context_block_respects_char_budget():
    block, truncated = build_context_block([_chunk("x" * 100), _chunk("y" * 100)], char_budget=120)
    assert truncated is True
    assert "y" not in block  # second chunk dropped, first kept whole


def test_ask_prompt_contains_question_and_context():
    prompt = build_ask_prompt("What is elasticity?", "[1] (m) context here")
    assert "What is elasticity?" in prompt
    assert "[1] (m) context here" in prompt


def test_explain_prompt_asks_for_definition_intuition_example():
    prompt = build_explain_prompt("elasticity", "[1] (m) ctx")
    for part in ("definition", "intuition", "example"):
        assert part in prompt.lower()


def test_summary_prompt_includes_title_and_chunks_in_order():
    prompt = build_summary_prompt("Supply & Demand", ["first chunk", "second chunk"])
    assert "Supply & Demand" in prompt
    assert prompt.index("first chunk") < prompt.index("second chunk")


def test_review_prompt_lists_notes_with_matches():
    items = [
        ReviewItem(note_content="wrong note", matched_content="what was said", similarity=0.3),
        ReviewItem(note_content="orphan note", matched_content=None, similarity=None),
    ]
    prompt = build_review_prompt(items)
    assert "wrong note" in prompt
    assert "what was said" in prompt
    assert "orphan note" in prompt


def test_grounded_system_prompt_demands_citations():
    assert "context" in GROUNDED_SYSTEM_PROMPT.lower()
    assert "cite" in GROUNDED_SYSTEM_PROMPT.lower()


def test_context_block_length_never_exceeds_budget():
    chunks = [_chunk("x" * 50), _chunk("y" * 50), _chunk("z" * 50)]
    budget = len("[1] (econ_notes.md) " + "x" * 50) + len("[2] (econ_notes.md) " + "y" * 50) + 1
    block, truncated = build_context_block(chunks, char_budget=budget)
    assert len(block) <= budget
    assert truncated is True
