"""Day 2 Task 2: TF-IDF similarity between chunks of different documents.

Loads the newest stored copy of A.pdf-D.pdf, fits TF-IDF on their chunks and prints the
strongest cross-document pairs. Nothing is written to the database.

    python scripts/verify_tfidf.py
    python scripts/verify_tfidf.py --top 25
    python scripts/verify_tfidf.py --documents A.pdf C.pdf
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import joinedload  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import Chunk, Document  # noqa: E402
from app.nlp.tfidf import ChunkPair, tfidf_cross_document_pairs  # noqa: E402

DEFAULT_DOCUMENTS = ["A.pdf", "B.pdf", "C.pdf", "D.pdf"]

# Text that marks the known XR-500 topics, used only to make the output easy to inspect.
TOPIC_MARKERS = {"pressure": "MPa", "temperature": "°C", "flow rate": "L/min"}
PAIRS_PER_TOPIC = 3
PREVIEW_CHARS = 110


def one_line(text: str) -> str:
    return " ".join(text.split())


def snippet(text: str, marker: str, width: int = 45) -> str:
    """The text around the first occurrence of marker."""
    text = one_line(text)
    at = text.find(marker)
    return "..." + text[max(at - width, 0):at + len(marker) + width] + "..."


def location(chunk: Chunk) -> str:
    return f"{chunk.document.filename} p{chunk.page_number}"


def load_chunks(db, filenames: list[str]) -> list[Chunk]:
    """Chunks of the newest stored copy of each file, with their document loaded."""
    chunks = []
    for filename in filenames:
        document = db.scalars(
            select(Document)
            .where(Document.filename == filename)
            .order_by(Document.uploaded_at.desc())
            .limit(1)
        ).first()
        if document is None:
            raise SystemExit(f"{filename} is not in the database. "
                             f"Run scripts/verify_chunk_storage.py on it first.")
        rows = db.scalars(
            select(Chunk)
            .options(joinedload(Chunk.document))
            .where(Chunk.document_id == document.id)
            .order_by(Chunk.page_number)
        ).all()
        print(f"  {filename:<10} {len(rows):>3} chunks  (document {document.id})")
        chunks.extend(rows)
    return chunks


def print_pair(rank: int, pair: ChunkPair) -> None:
    shared = [m for m in TOPIC_MARKERS.values() if m in pair.chunk_a.text and m in pair.chunk_b.text]
    print(f"\n#{rank:<3} score {pair.score:.3f}   {location(pair.chunk_a)}  <->  {location(pair.chunk_b)}"
          f"   both mention: {', '.join(shared) or '-'}")
    for chunk in (pair.chunk_a, pair.chunk_b):
        print(f"     {location(chunk):<10} {one_line(chunk.text)[:PREVIEW_CHARS]}...")


def main() -> None:
    parser = argparse.ArgumentParser(description="Show the strongest TF-IDF cross-document pairs.")
    parser.add_argument("--top", type=int, default=15, help="number of pairs to print")
    parser.add_argument("--documents", nargs="+", default=DEFAULT_DOCUMENTS,
                        help="filenames of the stored documents to compare")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")

    print("Loaded from PostgreSQL:")
    with SessionLocal() as db:
        chunks = load_chunks(db, args.documents)

    pairs = tfidf_cross_document_pairs(chunks)

    all_pairs = len(chunks) * (len(chunks) - 1) // 2
    assert all(p.chunk_a.document_id != p.chunk_b.document_id for p in pairs), "same-document pair found"
    print(f"\n{len(chunks)} chunks -> {all_pairs} possible pairs; "
          f"{all_pairs - len(pairs)} same-document pairs excluded; {len(pairs)} cross-document pairs scored")
    print("TF-IDF similarity only shows related wording; it is not a contradiction verdict.")

    print(f"\n=== Top {args.top} cross-document pairs by TF-IDF cosine similarity ===")
    for rank, pair in enumerate(pairs[:args.top], start=1):
        print_pair(rank, pair)

    print("\n=== Strongest pairs where both chunks mention a known topic ===")
    for topic, marker in TOPIC_MARKERS.items():
        print(f"\n{topic} ({marker}):")
        matches = [
            (rank, pair) for rank, pair in enumerate(pairs, start=1)
            if marker in pair.chunk_a.text and marker in pair.chunk_b.text
        ][:PAIRS_PER_TOPIC]
        if not matches:
            print("  no cross-document pair mentions it in both chunks")
        for rank, pair in matches:
            print(f"  #{rank:<3} score {pair.score:.3f}")
            for chunk in (pair.chunk_a, pair.chunk_b):
                print(f"     {location(chunk):<10} {snippet(chunk.text, marker)}")


if __name__ == "__main__":
    main()
