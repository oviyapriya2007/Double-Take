from dataclasses import dataclass
from pathlib import Path

import pymupdf

PdfSource = str | Path | bytes
"""A path to a PDF file, or the PDF's content."""


@dataclass
class ExtractedPage:
    page_number: int
    text: str


def _open(source: PdfSource) -> pymupdf.Document:
    if isinstance(source, bytes):
        return pymupdf.open(stream=source, filetype="pdf")
    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {path}")
    return pymupdf.open(path)


def extract_pages(source: PdfSource) -> list[ExtractedPage]:
    """Extract text from a PDF page by page, with 1-based page numbers.

    Pages with no text (after stripping whitespace) are skipped, so page
    numbers in the result may have gaps.
    """
    pages: list[ExtractedPage] = []
    with _open(source) as doc:
        for index, page in enumerate(doc):
            text = page.get_text("text").strip()
            if text:
                pages.append(ExtractedPage(page_number=index + 1, text=text))
    return pages


def read_title(source: PdfSource) -> str | None:
    """Return the PDF's metadata title, or None if it has none."""
    with _open(source) as doc:
        title = (doc.metadata or {}).get("title", "").strip()
    return title or None
