"""The real AIClient: NVIDIA Riva ASR + NIM embeddings + NIM chat.

Composes three adapters behind the single seam. Constructed only for real
runs (all adapters require an NVIDIA API key); tests override the DI
provider with FakeAIClient, so this is never built during the offline suite.
"""

from koherent.ai.base import Transcription
from koherent.ai.chat import NIMChatClient
from koherent.ai.embeddings import NIMEmbedder
from koherent.ai.riva import RivaClient


class RealAIClient:
    def __init__(self, transcriber=None, embedder=None, chat=None) -> None:
        self._transcriber = transcriber or RivaClient()
        self._embedder = embedder or NIMEmbedder()
        self._chat = chat or NIMChatClient()

    def transcribe(self, audio_path: str) -> Transcription:
        return self._transcriber.transcribe(audio_path)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._embedder.embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embedder.embed([text], input_type="query")[0]

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        return self._chat.generate(system_prompt, user_prompt)
