"""Day 2 Task 3: embed the A.pdf-D.pdf chunks with all-MiniLM-L6-v2 and store them.

    python scripts/verify_embeddings.py

Writes chunks.embedding for those chunks (no other column), reads the vectors back from
PostgreSQL and checks them. It ends with the roadmap's Task 3 check: a pgvector
nearest-neighbour search from a known pressure chunk. The similarity scores are a
retrieval signal only, not contradiction verdicts.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
from sqlalchemy import select, text  # noqa: E402
from sqlalchemy.orm import joinedload  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import EMBEDDING_DIM, Chunk, Document  # noqa: E402
from app.nlp.embeddings import MODEL_NAME  # noqa: E402
from app.services.embedding_storage import embed_and_store_chunks  # noqa: E402

DOCUMENTS = ["A.pdf", "B.pdf", "C.pdf", "D.pdf"]
SAMPLE_VALUES = 5

# The known pressure chunk used for the nearest-neighbour check.
QUERY_DOCUMENT = "C.pdf"
QUERY_PHRASE = "Maximum System Operating Pressure"
NEIGHBOURS = 5


def one_line(text: str) -> str:
    return " ".join(text.split())


def location(chunk: Chunk) -> str:
    return f"{chunk.document.filename} p{chunk.page_number}"


def load_chunks(db) -> list[Chunk]:
    return list(
        db.scalars(
            select(Chunk)
            .join(Document)
            .options(joinedload(Chunk.document))
            .where(Document.filename.in_(DOCUMENTS))
            .order_by(Document.filename, Chunk.page_number, Chunk.id)
        )
    )


def check_nearest_neighbours(db, chunks: list[Chunk]) -> None:
    query = next(
        (c for c in chunks if c.document.filename == QUERY_DOCUMENT and QUERY_PHRASE in c.text),
        None,
    )
    if query is None:
        print(f"\nSkipped nearest-neighbour check: no {QUERY_DOCUMENT} chunk contains {QUERY_PHRASE!r}")
        return

    # ix_chunks_embedding (ivfflat) was built while the table was empty and searches only
    # one of its lists by default, so it can skip true neighbours. With a few dozen chunks
    # an exact scan is instant; this setting lasts only for the current transaction.
    db.execute(text("SET LOCAL enable_indexscan = off"))
    distance = Chunk.embedding.cosine_distance(query.embedding)
    rows = db.execute(
        select(Chunk, distance.label("distance"))
        .options(joinedload(Chunk.document))
        .where(Chunk.document_id != query.document_id, Chunk.embedding.is_not(None))
        .order_by(distance)
        .limit(NEIGHBOURS)
    ).all()

    print(f"\npgvector nearest neighbours (other documents) of the {location(query)} pressure chunk:")
    at = one_line(query.text).find(QUERY_PHRASE)
    print(f"  query: ...{one_line(query.text)[at:at + 90]}...")
    for rank, (chunk, dist) in enumerate(rows, start=1):
        mentions = "mentions MPa" if "MPa" in chunk.text else ""
        print(f"  #{rank} cosine similarity {1 - dist:.3f}  {location(chunk):<10} {mentions:<13}"
              f"{one_line(chunk.text)[:60]}...")
    assert any("MPa" in chunk.text for chunk, _ in rows), "no pressure chunk among the nearest neighbours"
    print("  OK: a pressure chunk from another document is among the nearest neighbours")


def main() -> None:
    sys.stdout.reconfigure(errors="replace")

    with SessionLocal() as db:
        chunks = load_chunks(db)
        if not chunks:
            raise SystemExit(f"None of {DOCUMENTS} is in the database. "
                             f"Run scripts/verify_chunk_storage.py on them first.")
        print(f"Loaded {len(chunks)} chunks from PostgreSQL:")
        for filename in DOCUMENTS:
            print(f"  {filename:<8}{sum(c.document.filename == filename for c in chunks):>4} chunks")

        print(f"\nEmbedding with {MODEL_NAME} ...")
        embed_and_store_chunks(db, chunks)
        db.commit()
        generated = {chunk.id: np.asarray(chunk.embedding) for chunk in chunks}
    print(f"Stored embeddings for {len(generated)} chunks")

    # Fresh session, so everything below is read back from PostgreSQL.
    with SessionLocal() as db:
        stored = load_chunks(db)
        missing = [c for c in stored if c.embedding is None]
        assert not missing, f"{len(missing)} chunks have no embedding"
        for chunk in stored:
            vector = np.asarray(chunk.embedding)
            assert vector.shape == (EMBEDDING_DIM,), f"chunk {chunk.id} has shape {vector.shape}"
            assert np.allclose(vector, generated[chunk.id], atol=1e-6), (
                f"stored embedding of chunk {chunk.id} differs from the generated one"
            )

        print(f"\nRead back {len(stored)} embeddings; missing: {len(missing)}")
        print("Samples (first chunk of each document):")
        firsts = {}
        for chunk in stored:
            firsts.setdefault(chunk.document.filename, chunk)
        for chunk in firsts.values():
            vector = np.asarray(chunk.embedding)
            values = ", ".join(f"{v:+.4f}" for v in vector[:SAMPLE_VALUES])
            print(f"  {location(chunk):<10} dim={vector.shape[0]}  length={np.linalg.norm(vector):.4f}  "
                  f"first {SAMPLE_VALUES}: [{values}, ...]")

        check_nearest_neighbours(db, stored)

    print(f"\nOK: all {len(stored)} chunks have a {EMBEDDING_DIM}-dimensional embedding in PostgreSQL, "
          "matching the generated vectors")


if __name__ == "__main__":
    main()
