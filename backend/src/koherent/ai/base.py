from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TranscriptWord:
    """One transcript word with its spoken time span, in milliseconds."""

    word: str
    start_ms: int
    end_ms: int


@dataclass(frozen=True)
class Transcription:
    """Result of transcribing audio: the full text plus per-word timestamps.

    `text` is the transcript as the ASR returns it (spaced and punctuated).
    `words` carries per-word start/end times, used to place notes on the lecture
    timeline. With Inverse Text Normalization disabled in the ASR config
    (`verbatim_transcripts=True` in riva.py), `text` and `words` line up
    token-for-token. Leaving ITN on rewrites the transcript and drops tokens from
    `words`, so the two stop matching — which is why we disable it.
    """

    text: str
    words: list[TranscriptWord]


class AIClient(Protocol):
    """The seam between Koherent and any AI backend.

    The pipeline depends only on this shape. FakeAIClient implements it for
    development/tests; NIMClient implements it against NVIDIA NIM later.
    """

    def transcribe(self, audio_path: str) -> Transcription:
        """Return the transcript (text + per-word timestamps) for the audio file."""
        ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text, in the same order."""
        ...
