"""Real transcription via NVIDIA Parakeet (Riva ASR), behind the AIClient seam.

This adapter has exactly one job: turn a lecture audio file into our
``Transcription`` (full text + per-word timestamps in milliseconds). Riva's own
response objects never leave this module — everything downstream depends only on
the ``Transcription`` shape, so swapping ASR backends later touches nothing else.

Riva covers the *transcription* half of the seam. Embeddings come from a separate
NIM endpoint; a later ``NIMClient`` composes a transcriber + an embedder behind
the single ``AIClient`` interface.
"""

import riva.client

from koherent.ai.base import Transcription, TranscriptWord
from koherent.config import settings

# NVIDIA's hosted Riva endpoint (NVCF) — you run no ASR server yourself.
_NVCF_URI = "grpc.nvcf.nvidia.com:443"
# parakeet-tdt-0.6b-v2 function id from build.nvidia.com; update if NVIDIA rotates it.
_PARAKEET_FUNCTION_ID = "d3fe9151-442b-4204-a70d-5fcc597fd610"


def _response_to_transcription(response) -> Transcription:
    """Translate a raw Riva offline-recognize response into our ``Transcription``.

    Pure (no network), so it is unit-testable with a hand-built fake response.
    This is the *only* place that knows Riva's shape; everything it returns is
    ours. ``response`` is left untyped on purpose — it is the opaque boundary we
    accept from Riva and immediately convert.

    Mapping decisions worth knowing:
    - We concatenate *all* result segments. A long lecture comes back as several
      ``results``; reading only ``results[0]`` would silently drop the rest.
    - ``text`` comes from the segment transcripts (complete, punctuated);
      ``words`` comes from the per-word offsets. The two are not strictly 1:1
      (Riva can omit e.g. a leading word from ``words``), so nothing downstream
      may assume ``len(words) == len(text.split())``.
    - Riva reports word offsets in milliseconds; we store them as ints.
    - No speech / empty response maps to an empty ``Transcription`` — not a crash.
    """
    text_parts: list[str] = []
    words: list[TranscriptWord] = []

    for result in response.results:
        if not result.alternatives:
            continue
        best = result.alternatives[0]  # max_alternatives=1 -> the single best hypothesis
        if best.transcript:
            text_parts.append(best.transcript.strip())
        for w in best.words:
            words.append(
                TranscriptWord(
                    word=w.word,
                    start_ms=int(w.start_time),
                    end_ms=int(w.end_time),
                )
            )

    return Transcription(text=" ".join(text_parts).strip(), words=words)


class RivaClient:
    """ASR adapter: a lecture WAV -> ``Transcription`` via hosted Parakeet.

    Construct once and reuse — the gRPC channel is built in ``__init__``. All
    NVIDIA-specific configuration is contained here so the pipeline stays
    Riva-agnostic.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        function_id: str = _PARAKEET_FUNCTION_ID,
        language_code: str = "en-US",
    ) -> None:
        key = api_key or settings.nvidia_api_key
        if not key:
            raise ValueError("NVIDIA API key is required (set NVIDIA_API_KEY).")

        auth = riva.client.Auth(
            uri=_NVCF_URI,
            use_ssl=True,
            metadata_args=[
                ["function-id", function_id],
                ["authorization", f"Bearer {key}"],
            ],
        )
        self._asr = riva.client.ASRService(auth)
        self._language_code = language_code

    def transcribe(self, audio_path: str) -> Transcription:
        """Transcribe the WAV at ``audio_path`` into text + per-word timestamps."""
        with open(audio_path, "rb") as fh:
            audio = fh.read()

        config = riva.client.RecognitionConfig(
            language_code=self._language_code,
            max_alternatives=1,
            enable_automatic_punctuation=True,
            enable_word_time_offsets=True,  # the flag that yields per-word timestamps
        )
        # Inverse Text Normalization rewrites the transcript and drops tokens from the
        # word-timestamp list, so `text` and `words` stop matching (verified: 112 words
        # vs 118 text tokens). verbatim_transcripts=True turns ITN off -> text and words
        # are exactly 1:1, with no readability cost on our samples. Chunking can then
        # trust `words` completely instead of working around missing words.
        config.verbatim_transcripts = True
        self._apply_audio_specs(config, audio_path)

        response = self._asr.offline_recognize(audio, config)
        return _response_to_transcription(response)

    @staticmethod
    def _apply_audio_specs(config, audio_path: str) -> None:
        """Set encoding + sample rate from the WAV header, with a 16k PCM fallback.

        The Riva helper reads the format straight from the file header, but it
        chokes on some headers; when it does we fall back to the format our
        capture pipeline records in (16 kHz mono LINEAR_PCM).
        """
        try:
            riva.client.add_audio_file_specs_to_config(config, audio_path)
        except Exception:  # noqa: BLE001 - helper is brittle across headers; fall back explicitly
            config.encoding = riva.client.AudioEncoding.LINEAR_PCM
            config.sample_rate_hertz = 16_000
