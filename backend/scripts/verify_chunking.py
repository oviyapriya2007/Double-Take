"""Extract the sample PDF, chunk it, and check every chunk's page_number and text."""

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.chunking import CHUNK_OVERLAP, CHUNK_SIZE, TextChunk, chunk_pages  # noqa: E402
from app.services.pdf_extraction import extract_pages  # noqa: E402

DEFAULT_PDF = Path(__file__).resolve().parents[2] / "data" / "sample_docs" / "sample_manual.pdf"
PREVIEW_COUNT = 5


def report(label: str, chunks: list[TextChunk], valid_pages: set[int]) -> None:
    print(f"\n--- {label}: {len(chunks)} chunk(s) ---")
    for chunk in chunks[:PREVIEW_COUNT]:
        preview = chunk.text.replace("\n", " ")[:60]
        print(f"[page {chunk.page_number}] section={chunk.section} | {preview}")

    for i, chunk in enumerate(chunks):
        assert chunk.page_number in valid_pages, f"chunk {i}: bad page_number {chunk.page_number}"
        assert chunk.text.strip(), f"chunk {i}: empty text"
    print(f"OK: all {len(chunks)} chunks have a valid page_number and non-empty text")


def main() -> None:
    pdf_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PDF
    document_id = uuid.uuid4()  # placeholder until chunks are stored in Task 6

    pages = extract_pages(pdf_path)
    valid_pages = {page.page_number for page in pages}
    print(f"{pdf_path.name}: {len(pages)} page(s) with text, page numbers {sorted(valid_pages)}")
    print(f"document_id (placeholder): {document_id}")

    report(
        f"default chunk_size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP}",
        chunk_pages(pages, document_id),
        valid_pages,
    )
    report(
        "small chunk_size=80, overlap=20 (forces pages to split)",
        chunk_pages(pages, document_id, chunk_size=80, chunk_overlap=20),
        valid_pages,
    )


if __name__ == "__main__":
    main()
