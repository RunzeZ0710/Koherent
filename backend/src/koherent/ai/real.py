"""The real AIClient: NVIDIA Riva ASR for transcription + NIM for embeddings.

Composes two adapters behind the single seam. Constructed only for real runs
(both adapters require an NVIDIA API key); tests override the DI provider with
FakeAIClient, so this is never built during the offline suite.
"""

from koherent.ai.base import Transcription
from koherent.ai.embeddings import NIMEmbedder
from koherent.ai.riva import RivaClient


class RealAIClient:
    def __init__(self, transcriber=None, embedder=None) -> None:
        self._transcriber = transcriber or RivaClient()
        self._embedder = embedder or NIMEmbedder()

    def transcribe(self, audio_path: str) -> Transcription:
        return self._transcriber.transcribe(audio_path)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._embedder.embed(texts)
