"""Day 1 hardcoded pair: send two manually chosen chunks to Claude.

Each chunk is picked from the newest stored copy of a PDF by a phrase that must match
exactly one of its chunks. With no arguments, the XR-500 C.pdf / D.pdf maximum-pressure
pair is used.

    python scripts/verify_claude_comparison.py --a A.pdf --b C.pdf \
        --phrase "Ambient Temperature"
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import Chunk, Document  # noqa: E402
from app.services.claude_analysis import Statement, compare_statements  # noqa: E402

DEFAULT_A = "C.pdf"
DEFAULT_B = "D.pdf"
DEFAULT_PHRASE_A = "Maximum System Operating Pressure"
DEFAULT_PHRASE_B = "Fluid System Maximum Pressure Rating"


def parse_pair_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare two manually chosen chunks.")
    parser.add_argument("--a", default=DEFAULT_A, help="filename of document A")
    parser.add_argument("--b", default=DEFAULT_B, help="filename of document B")
    parser.add_argument("--phrase", help="text identifying the chunk in both documents")
    parser.add_argument("--phrase-a", help="text identifying the chunk in A (overrides --phrase)")
    parser.add_argument("--phrase-b", help="text identifying the chunk in B (overrides --phrase)")
    args = parser.parse_args()
    args.phrase_a = args.phrase_a or args.phrase or DEFAULT_PHRASE_A
    args.phrase_b = args.phrase_b or args.phrase or DEFAULT_PHRASE_B
    return args


def load_chunk(db, filename: str, phrase: str) -> tuple[Chunk, Document]:
    """The single chunk containing `phrase` in the newest stored copy of `filename`."""
    document = db.scalars(
        select(Document)
        .where(Document.filename == filename)
        .order_by(Document.uploaded_at.desc())
        .limit(1)
    ).first()
    if document is None:
        raise SystemExit(f"{filename} is not in the database. "
                         f"Run scripts/verify_chunk_storage.py on it first.")

    matches = db.scalars(
        select(Chunk)
        .where(Chunk.document_id == document.id, Chunk.text.contains(phrase))
        .order_by(Chunk.page_number)
    ).all()
    if not matches:
        raise SystemExit(f"No chunk in {filename} contains {phrase!r}.")
    if len(matches) > 1:
        listing = "\n".join(
            f"  page {c.page_number}: {' '.join(c.text.split())[:80]}" for c in matches
        )
        raise SystemExit(f"{len(matches)} chunks in {filename} contain {phrase!r}; "
                         f"use a more specific phrase:\n{listing}")
    return matches[0], document


def load_pair(db, args: argparse.Namespace) -> tuple[tuple[Chunk, Document], tuple[Chunk, Document]]:
    return load_chunk(db, args.a, args.phrase_a), load_chunk(db, args.b, args.phrase_b)


def to_statement(chunk: Chunk, document: Document) -> Statement:
    return Statement(
        text=chunk.text,
        document=document.filename,
        page=chunk.page_number,
        section=chunk.section,
        entities=[
            (entity.entity_type, entity.entity_text)
            for entity in sorted(chunk.entities, key=lambda e: e.start_char or 0)
            if entity.entity_type and entity.entity_text
        ],
    )


def main() -> None:
    args = parse_pair_args()
    with SessionLocal() as db:
        (chunk_a, doc_a), (chunk_b, doc_b) = load_pair(db, args)
        a, b = to_statement(chunk_a, doc_a), to_statement(chunk_b, doc_b)

    for label, chunk, s in (("A", chunk_a, a), ("B", chunk_b, b)):
        print(f"Statement {label}: chunk {chunk.id} | {s.document}, page {s.page}")
        print("  " + s.text.replace("\n", "\n  "))
        print(f"  entities: {s.entities}")
    print("\nCalling Claude...\n")

    result = compare_statements(a, b)

    print("Parsed ContradictionVerdict (Pydantic validation passed):")
    print(result.model_dump_json(indent=2))

    for field in ("verdict", "topic", "reasoning", "confidence", "evidence"):
        assert getattr(result, field) not in (None, "", []), f"missing {field}"
    print("\nOK: verdict, topic, reasoning, confidence and evidence are all present")


if __name__ == "__main__":
    main()
