import pytest

from koherent.pipeline.text_chunking import TextChunk, chunk_text


def test_empty_text_returns_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_short_text_is_one_chunk():
    chunks = chunk_text("Supply and demand set prices.")
    assert chunks == [TextChunk(index=0, content="Supply and demand set prices.")]


def test_short_paragraphs_merge_into_one_chunk():
    text = "First paragraph here.\n\nSecond paragraph here."
    chunks = chunk_text(text, target_words=50, overlap_words=10)
    assert len(chunks) == 1
    assert "First paragraph" in chunks[0].content
    assert "Second paragraph" in chunks[0].content


def test_paragraph_boundary_starts_new_chunk_when_target_exceeded():
    para_a = " ".join(f"a{i}" for i in range(40))
    para_b = " ".join(f"b{i}" for i in range(40))
    chunks = chunk_text(f"{para_a}\n\n{para_b}", target_words=50, overlap_words=10)
    assert len(chunks) == 2
    assert chunks[0].content == para_a
    assert chunks[1].content == para_b


def test_long_paragraph_splits_with_overlap():
    words = [f"w{i}" for i in range(120)]
    chunks = chunk_text(" ".join(words), target_words=50, overlap_words=10)
    assert len(chunks) == 3
    first_words = chunks[0].content.split()
    second_words = chunks[1].content.split()
    assert first_words[-10:] == second_words[:10]  # overlap carried over
    assert [c.index for c in chunks] == [0, 1, 2]


def test_overlap_must_be_smaller_than_target():
    with pytest.raises(ValueError):
        chunk_text("some text", target_words=10, overlap_words=10)
