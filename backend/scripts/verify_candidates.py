"""Day 2 Task 4: automatic candidate-pair generation over all stored chunks.

    python scripts/verify_candidates.py
    python scripts/verify_candidates.py --top 40

Uses the chunks' stored embeddings (Task 3) and entities (Task 1), selects cross-document
candidate pairs with the combined retrieval score, and stores them in candidate_pairs
(method "combined"). Rerunning updates the same rows instead of adding duplicates.
The scores only say which pairs are worth comparing, not whether they contradict.

The check is blind: it knows nothing about which contradictions the documents contain. It
prints the top candidates with the full text of both chunks for manual inspection.
"""

import argparse
import math
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import joinedload  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import CandidatePair, Chunk, ContradictionResult, Document  # noqa: E402
from app.retrieval.candidates import (  # noqa: E402
    CANDIDATE_METHOD,
    MAX_CANDIDATES,
    W_EMBEDDING,
    W_ENTITY,
    W_TECHNICAL,
    W_TFIDF,
    Candidate,
    generate_candidates,
)
from app.services.candidate_storage import store_candidates  # noqa: E402
from app.services.entity_storage import load_entity_types  # noqa: E402

TEXT_WIDTH = 100


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
            .order_by(Document.filename, Chunk.page_number, Chunk.id)
        )
    )


def method_counts(db) -> tuple[int, int]:
    """(rows with CANDIDATE_METHOD, rows with any other method) in candidate_pairs."""
    count = select(func.count()).select_from(CandidatePair)
    ours = db.scalar(count.where(CandidatePair.method == CANDIDATE_METHOD))
    total = db.scalar(count)
    return ours, total - ours


def print_candidate(rank: int, c: Candidate) -> None:
    """Rank, both locations, the scores and the full text of both chunks."""
    print(f"\n{'-' * TEXT_WIDTH}")
    print(f"#{rank:<3} A: {location(c.chunk_a):<14} B: {location(c.chunk_b):<14} "
          f"combined {c.combined_score:.3f}  (tfidf {c.tfidf_score:.3f}  "
          f"embedding {c.embedding_score:.3f}  entity {c.entity_overlap:.3f}  "
          f"technical {c.technical_compatibility:.3f})")
    for label, chunk in (("A", c.chunk_a), ("B", c.chunk_b)):
        print(f"  [{label}] {location(chunk)}")
        print(textwrap.fill(one_line(chunk.text), width=TEXT_WIDTH,
                            initial_indent="      ", subsequent_indent="      "))


def check_stored(candidates: list[Candidate]) -> int:
    """Read candidate_pairs back and check it holds each candidate once; return how many."""
    expected = {frozenset((c.chunk_a.id, c.chunk_b.id)): c for c in candidates}
    with SessionLocal() as db:
        rows = db.scalars(
            select(CandidatePair).where(CandidatePair.method == CANDIDATE_METHOD)
        ).all()
        documents = dict(db.execute(select(Chunk.id, Chunk.document_id)).all())
        referenced = set(db.scalars(select(ContradictionResult.candidate_pair_id)))

    keys = [frozenset((row.chunk_a_id, row.chunk_b_id)) for row in rows]
    assert len(keys) == len(set(keys)), "duplicate candidate pairs stored"
    assert set(expected) <= set(keys), "some generated candidates were not stored"
    for row, key in zip(rows, keys):
        assert documents[row.chunk_a_id] != documents[row.chunk_b_id], "stored same-document pair"
        if key not in expected:
            # Kept from an earlier run only because a contradiction result refers to it.
            assert row.id in referenced, f"stale candidate pair {row.id} was not removed"
            continue
        c = expected[key]
        for stored, generated in (
            (row.tfidf_score, c.tfidf_score),
            (row.embedding_score, c.embedding_score),
            (row.entity_overlap_score, c.entity_overlap),
            (row.combined_score, c.combined_score),
        ):
            assert math.isclose(stored, generated, abs_tol=1e-9), f"scores of pair {row.id} differ"
    return len(expected)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate, show and store candidate pairs.")
    parser.add_argument("--top", type=int, default=15, help="number of candidates to print")
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")

    with SessionLocal() as db:
        chunks = load_chunks(db)
        if not chunks:
            raise SystemExit("No chunks in the database. Run scripts/verify_chunk_storage.py first.")
        if any(chunk.embedding is None for chunk in chunks):
            raise SystemExit("Some chunks have no embedding. Run scripts/verify_embeddings.py first.")
        entity_types = load_entity_types(db, [chunk.id for chunk in chunks])
        if not entity_types:
            raise SystemExit("No entities stored. Run scripts/verify_ner.py first.")

        print(f"Loaded {len(chunks)} chunks with stored embeddings and entities:")
        for filename in sorted({chunk.document.filename for chunk in chunks}):
            print(f"  {filename:<10}{sum(c.document.filename == filename for c in chunks):>4} chunks")

        selection = generate_candidates(chunks, entity_types)
        candidates = selection.candidates
        assert all(c.chunk_a.document_id != c.chunk_b.document_id for c in candidates), (
            "same-document pair generated"
        )
        assert selection.scored_pairs == selection.cross_document_pairs, (
            "some cross-document pairs were not given a combined score"
        )
        assert len(candidates) == min(MAX_CANDIDATES, selection.cross_document_pairs), (
            "unexpected number of candidates selected"
        )

        print(f"\ncombined = {1 - W_TECHNICAL:.2f} x ({W_TFIDF} x TF-IDF + {W_EMBEDDING} x embedding "
              f"+ {W_ENTITY} x entity-type overlap) + {W_TECHNICAL} x technical compatibility")
        print(f"Total chunks:                    {len(chunks)}")
        print(f"Cross-document pairs:            {selection.cross_document_pairs}")
        print(f"Pairs with a combined score:     {selection.scored_pairs}")
        print(f"Candidates selected:             {len(candidates)} (MAX_CANDIDATES = {MAX_CANDIDATES})")
        print("OK: every cross-document pair was scored; no same-document pair was generated")

        print(f"\n=== Top {min(args.top, len(candidates))} candidates by combined score ===")
        for rank, candidate in enumerate(candidates[:args.top], start=1):
            print_candidate(rank, candidate)
        print("-" * TEXT_WIDTH)

        before, others_before = method_counts(db)
        store_candidates(db, candidates)
        db.commit()
        after, others_after = method_counts(db)

    stored = check_stored(candidates)
    print(f"\ncandidate_pairs with method '{CANDIDATE_METHOD}': {before} rows before, {after} after "
          f"(other methods: {others_before} before, {others_after} after)")
    print(f"OK: {stored} candidate pairs stored once each, cross-document, scores match the generated ones")


if __name__ == "__main__":
    main()
