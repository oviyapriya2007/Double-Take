from sqlalchemy.orm import Session

from app.models import Chunk
from app.nlp.embeddings import embed_texts


def embed_and_store_chunks(db: Session, chunks: list[Chunk]) -> None:
    """Compute an embedding for each chunk and write it to chunks.embedding.

    Only the embedding column is updated; running this again overwrites it with the same
    vectors. The caller is responsible for committing.
    """
    for chunk, vector in zip(chunks, embed_texts([chunk.text for chunk in chunks])):
        chunk.embedding = vector
    db.flush()
