from koherent.ai.fake import FakeAIClient


def test_embed_is_deterministic_and_correct_length():
    ai = FakeAIClient()
    a = ai.embed(["marginal cost equals marginal revenue"])
    b = ai.embed(["marginal cost equals marginal revenue"])
    assert a == b                      # deterministic
    assert len(a) == 1                 # one vector per input
    assert len(a[0]) == FakeAIClient.DIM


def test_embed_shared_words_point_more_similarly_than_disjoint():
    import numpy as np

    ai = FakeAIClient()
    base, overlap, disjoint = ai.embed(
        ["supply and demand equilibrium", "supply and demand curve", "zebra igloo"]
    )

    def cos(x, y):
        x, y = np.array(x), np.array(y)
        return float(x.dot(y) / (np.linalg.norm(x) * np.linalg.norm(y)))

    assert cos(base, overlap) > cos(base, disjoint)


def test_transcribe_returns_transcription_with_words():
    from koherent.ai.base import Transcription

    ai = FakeAIClient()
    result = ai.transcribe("anything.webm")
    assert isinstance(result, Transcription)
    assert len(result.text) > 0
    assert len(result.words) > 0
    assert result.words[0].word == result.text.split()[0]


def test_transcribe_words_have_increasing_timestamps():
    ai = FakeAIClient()
    words = ai.transcribe("anything.webm").words
    starts = [w.start_ms for w in words]
    assert starts == sorted(starts)
    assert all(w.end_ms >= w.start_ms for w in words)


def test_transcribe_can_be_overridden():
    ai = FakeAIClient(transcript="custom lecture text")
    result = ai.transcribe("ignored.webm")
    assert result.text == "custom lecture text"
    assert [w.word for w in result.words] == ["custom", "lecture", "text"]
