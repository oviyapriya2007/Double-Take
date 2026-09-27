"""Day 1 hardcoded pair: send the two known contradictory temperature chunks to Claude."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import Chunk, Document  # noqa: E402
from app.services.claude_analysis import Statement, compare_statements  # noqa: E402

# Hardcoded known pair: the operating-temperature chunk from each sample manual.
PAIR_FILENAMES = ("sample_manual.pdf", "sample_manual_b.pdf")
PAIR_PHRASE = "Operating temperature"


def load_chunk(db, filename: str) -> tuple[Chunk, Document]:
    """Newest stored copy of `filename`'s chunk containing PAIR_PHRASE."""
    row = db.execute(
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(Document.filename == filename, Chunk.text.contains(PAIR_PHRASE))
        .order_by(Document.uploaded_at.desc())
        .limit(1)
    ).first()
    if row is None:
        raise SystemExit(f"No chunk containing {PAIR_PHRASE!r} found for {filename}. "
                         f"Run scripts/verify_chunk_storage.py on it first.")
    return row


def to_statement(chunk: Chunk, document: Document) -> Statement:
    return Statement(
        text=chunk.text,
        document=document.title or document.filename,
        page=chunk.page_number,
        section=chunk.section,
    )


def main() -> None:
    with SessionLocal() as db:
        (chunk_a, doc_a), (chunk_b, doc_b) = (load_chunk(db, f) for f in PAIR_FILENAMES)
        a, b = to_statement(chunk_a, doc_a), to_statement(chunk_b, doc_b)

    for label, chunk, s in (("A", chunk_a, a), ("B", chunk_b, b)):
        print(f"Statement {label}: chunk {chunk.id} | {s.document}, page {s.page}")
        print("  " + s.text.replace("\n", "\n  "))
    print("\nCalling Claude...\n")

    result = compare_statements(a, b)

    print("Parsed ContradictionVerdict (Pydantic validation passed):")
    print(result.model_dump_json(indent=2))

    for field in ("verdict", "topic", "reasoning", "confidence", "evidence"):
        assert getattr(result, field) not in (None, "", []), f"missing {field}"
    print("\nOK: verdict, topic, reasoning, confidence and evidence are all present")


if __name__ == "__main__":
    main()
