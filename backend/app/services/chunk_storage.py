from sqlalchemy.orm import Session

from app.models import Chunk, Document
from app.services.chunking import TextChunk


def create_document(
    db: Session,
    filename: str,
    title: str | None = None,
    doc_type: str | None = None,
) -> Document:
    """Add a document row and flush so its database-generated id is available.

    The caller is responsible for committing.
    """
    document = Document(filename=filename, title=title, doc_type=doc_type)
    db.add(document)
    db.flush()
    return document


def store_chunks(db: Session, chunks: list[TextChunk]) -> list[Chunk]:
    """Add chunk rows (tfidf_vector and embedding left NULL) and flush.

    The caller is responsible for committing.
    """
    rows = [
        Chunk(
            document_id=chunk.document_id,
            page_number=chunk.page_number,
            section=chunk.section,
            text=chunk.text,
        )
        for chunk in chunks
    ]
    db.add_all(rows)
    db.flush()
    return rows
