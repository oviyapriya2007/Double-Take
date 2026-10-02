from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Document
from app.services.chunk_storage import create_document, store_chunks
from app.services.chunking import chunk_pages
from app.services.pdf_extraction import extract_pages, read_title

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
"""Uploaded PDFs are kept here as <document id>.pdf."""

PDF_SIGNATURE = b"%PDF-"


class IngestionError(ValueError):
    """The file is not a readable, text-based PDF."""


@dataclass
class IngestedDocument:
    document: Document
    pages: int
    chunks: int
    path: Path


def looks_like_pdf(filename: str | None, content: bytes) -> bool:
    """True when the file has a .pdf extension and starts with the PDF signature."""
    return bool(filename) and filename.lower().endswith(".pdf") and content.startswith(PDF_SIGNATURE)


def ingest_uploaded_pdf(
    db: Session, filename: str, content: bytes, doc_type: str | None = None
) -> IngestedDocument:
    """Extract and chunk an uploaded PDF, add its document and chunk rows, and save the file.

    NER and embeddings are left to run_pipeline, which computes them for chunks that lack
    them. Raises IngestionError, before anything is stored, if the PDF cannot be read or
    has no extractable text (scanned PDFs are not supported). The caller is responsible
    for committing, and for deleting the returned path if it rolls back.
    """
    try:
        pages = extract_pages(content)
        title = read_title(content)
    except RuntimeError as exc:
        raise IngestionError(f"{filename} could not be read as a PDF") from exc
    if not pages:
        raise IngestionError(f"{filename} has no extractable text; scanned PDFs are not supported")

    document = create_document(db, filename=filename, title=title, doc_type=doc_type)
    chunks = store_chunks(db, chunk_pages(pages, document.id))

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = UPLOAD_DIR / f"{document.id}.pdf"
    path.write_bytes(content)
    return IngestedDocument(document=document, pages=len(pages), chunks=len(chunks), path=path)
