"""LLM text generation via NVIDIA NIM chat completions, behind the AIClient seam.

Same transport story as embeddings.py: NIM exposes an OpenAI-compatible
endpoint, so the OpenAI SDK is pointed at NVIDIA's base URL and one
NVIDIA_API_KEY covers ASR, embeddings, and generation. All NVIDIA chat
specifics are contained here.
"""
from openai import OpenAI

from koherent.config import settings

_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"


def _response_to_text(response) -> str:
    """Pure mapping from an OpenAI-style chat response to the completion text."""
    return response.choices[0].message.content or ""


class NIMChatClient:
    """Generation adapter: (system prompt, user prompt) -> completion text."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        client=None,
    ) -> None:
        if client is None:
            key = api_key or settings.nvidia_api_key
            if not key:
                raise ValueError("NVIDIA API key is required (set NVIDIA_API_KEY).")
            client = OpenAI(base_url=_NIM_BASE_URL, api_key=key)
        self._client = client
        self._model = model or settings.nim_chat_model
        self._temperature = temperature

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self._temperature,
        )
        return _response_to_text(response)
