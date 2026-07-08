import pytest

from koherent.pipeline.extraction import (
    EmptyDocumentError,
    UnsupportedDocumentError,
    extract_text,
)


def test_txt_roundtrip():
    assert extract_text(b"hello notes", "notes.txt") == "hello notes"


def test_md_roundtrip():
    assert extract_text(b"# Week 1\n\nSupply and demand.", "week1.md").startswith("# Week 1")


def test_unsupported_suffix_raises():
    with pytest.raises(UnsupportedDocumentError):
        extract_text(b"...", "slides.docx")


def test_empty_document_raises():
    with pytest.raises(EmptyDocumentError):
        extract_text(b"   \n ", "empty.txt")


def test_pdf_pages_are_joined(monkeypatch):
    class FakePage:
        def __init__(self, text):
            self._text = text

        def extract_text(self):
            return self._text

    class FakeReader:
        def __init__(self, stream):
            self.pages = [FakePage("page one"), FakePage("page two")]

    monkeypatch.setattr("koherent.pipeline.extraction.PdfReader", FakeReader)
    assert extract_text(b"%PDF-fake", "doc.pdf") == "page one\n\npage two"


def test_blank_pdf_raises_empty(monkeypatch):
    class FakePage:
        def extract_text(self):
            return None

    class FakeReader:
        def __init__(self, stream):
            self.pages = [FakePage()]

    monkeypatch.setattr("koherent.pipeline.extraction.PdfReader", FakeReader)
    with pytest.raises(EmptyDocumentError):
        extract_text(b"%PDF-fake", "doc.pdf")


def test_malformed_pdf_raises_empty_document_error():
    with pytest.raises(EmptyDocumentError):
        extract_text(b"not a real pdf at all", "doc.pdf")
