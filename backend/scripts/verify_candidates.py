"""Day 2 Task 4: automatic candidate-pair generation over all stored chunks.

    python scripts/verify_candidates.py
    python scripts/verify_candidates.py --top 40

Uses the chunks' stored embeddings (Task 3) and entities (Task 1), selects cross-document
candidate pairs with the combined retrieval score, and stores them in candidate_pairs
(method "combined"). Rerunning updates the same rows instead of adding duplicates.
The scores only say which pairs are worth comparing, not whether they contradict.
"""

import argparse
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.orm import joinedload  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import CandidatePair, Chunk, ContradictionResult, Document  # noqa: E402
from app.retrieval.candidates import (  # noqa: E402
    CANDIDATE_METHOD,
    TOP_K_PER_CHUNK,
    W_EMBEDDING,
    W_ENTITY,
    W_TFIDF,
    Candidate,
    generate_candidates,
)
from app.services.candidate_storage import store_candidates  # noqa: E402
from app.services.entity_storage import load_entity_types  # noqa: E402

# Conflicting values planted in the XR-500 demo documents. A candidate "covers" a topic when
# its two chunks mention different values from the same list. Used only to inspect the
# output; it plays no part in selecting candidates.
KNOWN_CONFLICTS = {
    "maximum pressure": ["2.8 MPa", "3.5 MPa", "1.8 MPa"],
    "minimum flow rate": ["40 L/min", "50 L/min"],
    "ambient temperature": ["50°C", "55°C"],
}
PAIRS_PER_TOPIC = 5
SNIPPET_CHARS = 70


def one_line(text: str) -> str:
    return " ".join(text.split())


def location(chunk: Chunk) -> str:
    return f"{chunk.document.filename} p{chunk.page_number}"


def values_in(text: str, values: list[str]) -> set[str]:
    text = one_line(text)
    return {v for v in values if re.search(rf"(?<![\d.]){re.escape(v)}", text)}


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
    print(f"\n#{rank:<3} combined {c.combined_score:.3f} | tfidf {c.tfidf_score:.3f}  "
          f"embedding {c.embedding_score:.3f}  entity {c.entity_overlap:.3f} | "
          f"{location(c.chunk_a)} <-> {location(c.chunk_b)}")
    for chunk in (c.chunk_a, c.chunk_b):
        print(f"     {location(chunk):<10} {one_line(chunk.text)[:SNIPPET_CHARS]}...")


def print_known_conflicts(candidates: list[Candidate]) -> list[str]:
    """Print which candidates cover each known conflict; return the topics not covered."""
    print("\n=== Known XR-500 conflicts among the candidates (inspection only, not a verdict) ===")
    missing = []
    for topic, values in KNOWN_CONFLICTS.items():
        hits = []
        for rank, c in enumerate(candidates, start=1):
            a, b = values_in(c.chunk_a.text, values), values_in(c.chunk_b.text, values)
            if a and b and a != b:
                hits.append((rank, c, a, b))
        status = f"{len(hits)} candidate pairs, best rank #{hits[0][0]}" if hits else "NOT FOUND"
        print(f"\n{topic} ({' / '.join(values)}): {status}")
        if not hits:
            missing.append(topic)
        for rank, c, a, b in hits[:PAIRS_PER_TOPIC]:
            print(f"  #{rank:<3} combined {c.combined_score:.3f}   "
                  f"{location(c.chunk_a)} [{', '.join(sorted(a))}]  <->  "
                  f"{location(c.chunk_b)} [{', '.join(sorted(b))}]")
    return missing


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
    parser.add_argument("--top", type=int, default=20, help="number of candidates to print")
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

        print(f"\ncombined = {W_TFIDF} x TF-IDF + {W_EMBEDDING} x embedding "
              f"+ {W_ENTITY} x entity-type overlap")
        print(f"Total chunks:                    {len(chunks)}")
        print(f"Cross-document pairs considered: {selection.cross_document_pairs}")
        print(f"Shortlisted pairs:               {selection.shortlisted_pairs} "
              f"(top {TOP_K_PER_CHUNK} embedding neighbours of each chunk)")
        print(f"Candidates selected:             {len(candidates)}")
        print("OK: no same-document pair was generated")

        print(f"\n=== Top {min(args.top, len(candidates))} candidates by combined score ===")
        for rank, candidate in enumerate(candidates[:args.top], start=1):
            print_candidate(rank, candidate)

        missing = print_known_conflicts(candidates)

        before, others_before = method_counts(db)
        store_candidates(db, candidates)
        db.commit()
        after, others_after = method_counts(db)

    stored = check_stored(candidates)
    print(f"\ncandidate_pairs with method '{CANDIDATE_METHOD}': {before} rows before, {after} after "
          f"(other methods: {others_before} before, {others_after} after)")
    print(f"OK: {stored} candidate pairs stored once each, cross-document, scores match the generated ones")
    if missing:
        print(f"WARNING: known conflicts not among the candidates: {', '.join(missing)}")
    else:
        print("OK: the known pressure, flow-rate and temperature conflicts are all among the candidates")


if __name__ == "__main__":
    main()
