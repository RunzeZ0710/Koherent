from typing import Protocol


class AIClient(Protocol):
    """The seam between Koherent and any AI backend.

    The pipeline depends only on this shape. FakeAIClient implements it for
    development/tests; NIMClient implements it against NVIDIA NIM later.
    """

    def transcribe(self, audio_path: str) -> str:
        """Return the transcript text for the audio file at `audio_path`."""
        ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text, in the same order."""
        ...
