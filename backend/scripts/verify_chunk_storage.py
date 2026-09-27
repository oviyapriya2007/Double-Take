"""Extract the sample PDF, chunk it, store it in PostgreSQL, then read it back and check it.

Each run creates a new document row (with its chunks); earlier runs are not removed.
"""

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import Chunk, Document  # noqa: E402
from app.services.chunk_storage import create_document, store_chunks  # noqa: E402
from app.services.chunking import chunk_pages  # noqa: E402
from app.services.pdf_extraction import extract_pages, read_title  # noqa: E402

DEFAULT_PDF = Path(__file__).resolve().parents[2] / "data" / "sample_docs" / "sample_manual.pdf"


def main() -> None:
    pdf_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PDF

    pages = extract_pages(pdf_path)
    with SessionLocal() as db:
        document = create_document(db, filename=pdf_path.name, title=read_title(pdf_path))
        chunks = chunk_pages(pages, document.id)
        store_chunks(db, chunks)
        db.commit()
        document_id = document.id

    expected = Counter((c.page_number, c.text) for c in chunks)

    # Fresh session, so everything below is read back from PostgreSQL.
    with SessionLocal() as db:
        stored_doc = db.get(Document, document_id)
        rows = db.scalars(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.page_number)
        ).all()

        print(f"document id : {stored_doc.id}")
        print(f"filename    : {stored_doc.filename}")
        print(f"title       : {stored_doc.title}")
        print(f"doc_type    : {stored_doc.doc_type}")
        print(f"uploaded_at : {stored_doc.uploaded_at}")
        print(f"chunks      : {len(rows)}\n")
        for row in rows:
            preview = row.text.replace("\n", " ")[:50]
            print(f"{row.id}  page={row.page_number}  section={row.section}  | {preview}")

        actual = Counter((r.page_number, r.text) for r in rows)
        assert actual == expected, "stored chunks do not match the chunker output"
        assert all(r.section == "unknown" for r in rows), "unexpected section value"
        assert all(r.tfidf_vector is None and r.embedding is None for r in rows), (
            "tfidf_vector/embedding should be NULL on Day 1"
        )
        stored_pages = sorted({r.page_number for r in rows})
        assert stored_pages == [p.page_number for p in pages], "page numbers do not match"

    print(f"\nOK: {len(rows)} chunks stored for pages {stored_pages}; text, page numbers and "
          "section match the chunker output; tfidf_vector and embedding are NULL")


if __name__ == "__main__":
    main()
