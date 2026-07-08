"""Extract plain text from uploaded course-material documents.

Dispatch is by filename suffix — browsers are unreliable about MIME types
for .md files, and the suffix is what users actually see. PDF extraction
uses pypdf; scanned/image-only PDFs yield no text and are rejected as
empty rather than silently ingested as blank chunks.
"""
import io
from pathlib import Path

from pypdf import PdfReader


class UnsupportedDocumentError(ValueError):
    """Document type we do not ingest (route layer maps this to HTTP 415)."""


class EmptyDocumentError(ValueError):
    """No extractable text (route layer maps this to HTTP 422)."""


_TEXT_SUFFIXES = {".txt", ".md"}


def extract_text(data: bytes, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        text = data.decode("utf-8", errors="replace")
    elif suffix == ".pdf":
        try:
            reader = PdfReader(io.BytesIO(data))
            text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as e:
            raise EmptyDocumentError("Could not extract text from PDF (file may be corrupt)") from e
    else:
        raise UnsupportedDocumentError(f"Unsupported document type: {suffix or '(none)'}")
    if not text.strip():
        raise EmptyDocumentError("Document contains no extractable text")
    return text.strip()
