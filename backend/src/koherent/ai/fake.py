import hashlib

from koherent.ai.base import Transcription, TranscriptWord

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
    _WORD_MS = 400  # synthetic cadence: one word every 400ms

    def __init__(self, transcript: str = DEFAULT_TRANSCRIPT) -> None:
        self._transcript = transcript

    def transcribe(self, audio_path: str) -> Transcription:
        words: list[TranscriptWord] = []
        for i, token in enumerate(self._transcript.split()):
            start = i * self._WORD_MS
            words.append(TranscriptWord(word=token, start_ms=start, end_ms=start + 300))
        return Transcription(text=self._transcript, words=words)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self.DIM
        for word in text.lower().split():
            bucket = int(hashlib.md5(word.encode()).hexdigest(), 16) % self.DIM
            vec[bucket] += 1.0
        return vec

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        # Judge prompts (see pipeline/judge.py) need parseable JSON to keep the
        # eval harness runnable offline; everything else gets a deterministic
        # tag so tests can assert both stability and prompt-sensitivity.
        if "Return ONLY JSON" in system_prompt:
            return '{"claims": [{"text": "fake claim", "verdict": "supported"}]}'
        digest = hashlib.md5(f"{system_prompt}\n\n{user_prompt}".encode()).hexdigest()[:8]
        return f"[fake:{digest}] {user_prompt[:160]}"
