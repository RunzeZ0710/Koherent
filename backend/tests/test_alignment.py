import math

import pytest

from koherent.pipeline.alignment import AlignmentResult, align, cosine


# --------------------------------------------------------------------------
# cosine(a, b): how aligned are two arrows? 1 = same dir, 0 = unrelated, -1 = opposite
# --------------------------------------------------------------------------

def test_cosine_identical_vectors_is_one():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_cosine_orthogonal_vectors_is_zero():
    assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_opposite_vectors_is_minus_one():
    assert cosine([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)


def test_cosine_known_45_degree_value():
    # the angle between [1,0] and [1,1] is 45 degrees, whose cosine is 1/sqrt(2)
    assert cosine([1.0, 0.0], [1.0, 1.0]) == pytest.approx(1 / math.sqrt(2))


def test_cosine_zero_vector_returns_zero_not_crash():
    # a zero vector has no direction -> defined as 0.0, and must NOT divide by zero
    assert cosine([0.0, 0.0], [1.0, 2.0]) == 0.0


# --------------------------------------------------------------------------
# align(notes, chunks): for each note, pick the chunk with the highest cosine
# --------------------------------------------------------------------------

def test_align_picks_the_most_similar_chunk():
    notes = [[1.0, 0.0]]
    chunks = [[0.0, 1.0], [0.9, 0.1], [1.0, 0.0]]  # chunk 2 is identical to the note
    result = align(notes, chunks)
    assert len(result) == 1
    assert result[0].note_index == 0
    assert result[0].chunk_index == 2
    assert result[0].similarity == pytest.approx(1.0)


def test_align_handles_each_note_independently():
    notes = [[1.0, 0.0], [0.0, 1.0]]
    chunks = [[1.0, 0.0], [0.0, 1.0]]
    result = align(notes, chunks)
    assert [r.chunk_index for r in result] == [0, 1]  # note 0 -> chunk 0, note 1 -> chunk 1


def test_align_breaks_ties_by_earliest_chunk():
    notes = [[1.0, 0.0]]
    chunks = [[1.0, 0.0], [1.0, 0.0]]  # both identical -> tie
    result = align(notes, chunks)
    assert result[0].chunk_index == 0


def test_align_no_notes_yields_no_results():
    assert align([], [[1.0, 0.0]]) == []


def test_align_no_chunks_yields_no_results():
    assert align([[1.0, 0.0]], []) == []
