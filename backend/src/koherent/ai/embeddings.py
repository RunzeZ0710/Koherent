"""Real embeddings via NVIDIA NIM (`nvidia/nv-embedqa-e5-v5`), behind the AIClient seam.

This adapter turns texts into vectors. NIM exposes an OpenAI-compatible
embeddings endpoint, so we use the OpenAI SDK pointed at NVIDIA's base URL.
The query/passage asymmetry of embedqa models is handled with `input_type`;
queries are now embedded as "query" via the per-call override. All NVIDIA
specifics are contained here.
"""

from openai import OpenAI

from koherent.config import settings

_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
_EMBED_MODEL = "nvidia/nv-embedqa-e5-v5"


def _response_to_vectors(response) -> list[list[float]]:
    """Pure mapping from an OpenAI-style embeddings response to plain vectors.

    Order is preserved (item i corresponds to input text i). Untyped on
    purpose — this is the boundary we accept from the SDK and immediately
    convert, so nothing downstream depends on the SDK's shape.
    """
    return [list(item.embedding) for item in response.data]


class NIMEmbedder:
    """Embeddings adapter: list[str] -> list[vector] via hosted NIM."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = _EMBED_MODEL,
        input_type: str = "passage",
        client=None,
    ) -> None:
        if client is None:
            key = api_key or settings.nvidia_api_key
            if not key:
                raise ValueError("NVIDIA API key is required (set NVIDIA_API_KEY).")
            client = OpenAI(base_url=_NIM_BASE_URL, api_key=key)
        self._client = client
        self._model = model
        self._input_type = input_type

    def embed(self, texts: list[str], *, input_type: str | None = None) -> list[list[float]]:
        if not texts:
            return []
        response = self._client.embeddings.create(
            model=self._model,
            input=texts,
            extra_body={"input_type": input_type or self._input_type, "truncate": "END"},
        )
        return _response_to_vectors(response)
