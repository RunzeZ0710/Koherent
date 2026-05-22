import uuid
from pathlib import Path

from koherent.config import settings


def storage_root() -> Path:
    root = Path(settings.audio_storage_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_audio(content: bytes, suffix: str = ".webm") -> str:
    """Write `content` to disk under the configured storage root.
    Returns a path relative to the storage root."""
    root = storage_root()
    name = f"{uuid.uuid4()}{suffix}"
    (root / name).write_bytes(content)
    return name
