from koherent.ai.base import TranscriptWord
from koherent.pipeline.chunking import ChunkText, chunk_transcript


def test_groups_words_in_same_bucket_into_one_chunk():
    words = [
        TranscriptWord("a", 0, 400),
        TranscriptWord("b", 600, 900),
        TranscriptWord("c", 1100, 1400),
    ]
    chunks = chunk_transcript(words, chunk_ms=2000)
    assert chunks == [ChunkText(index=0, content="a b c", start_ms=0, end_ms=1400)]


def test_splits_into_separate_chunks_across_buckets():
    words = [
        TranscriptWord("a", 0, 400),
        TranscriptWord("b", 600, 900),
        TranscriptWord("c", 2300, 2600),  # bucket 1
    ]
    chunks = chunk_transcript(words, chunk_ms=2000)
    assert chunks == [
        ChunkText(index=0, content="a b", start_ms=0, end_ms=900),
        ChunkText(index=1, content="c", start_ms=2300, end_ms=2600),
    ]


def test_skips_empty_buckets_and_indexes_sequentially():
    # bucket 0 then bucket 2 (silence in bucket 1) -> indices stay 0,1, no crash.
    words = [TranscriptWord("a", 0, 400), TranscriptWord("b", 4500, 4800)]
    chunks = chunk_transcript(words, chunk_ms=2000)
    assert chunks == [
        ChunkText(index=0, content="a", start_ms=0, end_ms=400),
        ChunkText(index=1, content="b", start_ms=4500, end_ms=4800),
    ]


def test_empty_words_yields_no_chunks():
    assert chunk_transcript([]) == []


def test_single_word_is_one_chunk():
    chunks = chunk_transcript([TranscriptWord("a", 0, 400)], chunk_ms=2000)
    assert chunks == [ChunkText(index=0, content="a", start_ms=0, end_ms=400)]
