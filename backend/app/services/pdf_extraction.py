from dataclasses import dataclass
from pathlib import Path

import pymupdf


@dataclass
class ExtractedPage:
    page_number: int
    text: str


def extract_pages(pdf_path: str | Path) -> list[ExtractedPage]:
    """Extract text from a PDF page by page, with 1-based page numbers.

    Pages with no text (after stripping whitespace) are skipped, so page
    numbers in the result may have gaps.
    """
    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF not found: {path}")

    pages: list[ExtractedPage] = []
    with pymupdf.open(path) as doc:
        for index, page in enumerate(doc):
            text = page.get_text("text").strip()
            if text:
                pages.append(ExtractedPage(page_number=index + 1, text=text))
    return pages


def read_title(pdf_path: str | Path) -> str | None:
    """Return the PDF's metadata title, or None if it has none."""
    with pymupdf.open(Path(pdf_path)) as doc:
        title = (doc.metadata or {}).get("title", "").strip()
    return title or None
