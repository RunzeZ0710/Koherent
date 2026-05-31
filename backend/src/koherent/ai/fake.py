import hashlib

DEFAULT_TRANSCRIPT = (
    "Today we covered supply and demand. The market reaches equilibrium where "
    "the supply curve crosses the demand curve. A firm maximizes profit where "
    "marginal revenue equals marginal cost. A price floor set above equilibrium "
    "creates a surplus."
)


class FakeAIClient:
    """Deterministic, network-free AIClient for development and tests.

    `embed` is a hashed bag-of-words: each word is hashed (md5, for
    cross-run determinism) into one of DIM buckets and counted. Identical text
    yields identical vectors; shared words yield similar directions.
    """

    DIM = 64

    def __init__(self, transcript: str = DEFAULT_TRANSCRIPT) -> None:
        self._transcript = transcript

    def transcribe(self, audio_path: str) -> str:
        return self._transcript

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.DIM
        for word in text.lower().split():
            bucket = int(hashlib.md5(word.encode()).hexdigest(), 16) % self.DIM
            vec[bucket] += 1.0
        return vec
