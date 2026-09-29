"""Temporary diagnostic: score EVERY cross-document chunk pair, before any filtering.

    python scripts/diagnose_candidates.py
    python scripts/diagnose_candidates.py --top 30 --preview 400
    python scripts/diagnose_candidates.py --find "text in A" "text in B" --find ...

Uses the stored documents whose filenames match the PDFs in --folder (newest stored copy of
each), their stored chunks, embeddings and entity types. Chunks with no stored entities or
embedding get them computed in memory only. Nothing is written to the database.

Every cross-document pair is scored with the production helpers and weights from
app.retrieval.candidates and checked against generate_candidates(): with an unlimited budget
it must return every pair with the same scores, and with the real budget it marks which
pairs are selected. The full ranked list is written to --output as CSV.

--find A B (repeatable) prints the rank of every pair where one chunk contains A and the other
contains B (case-insensitive substrings), to check where specific relationships rank.
"""

import argparse
import csv
import sys
import textwrap
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import joinedload  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import Chunk, Document  # noqa: E402
from app.nlp.embeddings import embed_texts  # noqa: E402
from app.nlp.ner import extract_entities  # noqa: E402
from app.nlp.technical_claims import (  # noqa: E402
    claim_compatibility,
    extract_technical_claims,
    technical_compatibility,
)
from app.nlp.tfidf import tfidf_similarity_matrix  # noqa: E402
from app.retrieval.candidates import (  # noqa: E402
    MAX_CANDIDATES,
    W_EMBEDDING,
    W_ENTITY,
    W_TECHNICAL,
    W_TFIDF,
    combined_score,
    embedding_similarity_matrix,
    entity_overlap,
    generate_candidates,
)
from app.services.entity_storage import load_entity_types  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FOLDER = PROJECT_ROOT / "data" / "sample_docs" / "test_ei"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "candidate_diagnostics_ei.csv"
TEXT_WIDTH = 110


@dataclass
class ScoredPair:
    i: int
    j: int
    tfidf: float
    embedding: float
    entity: float
    technical: float
    combined: float
    claim_a: str = ""
    claim_b: str = ""
    """The best-matching technical claims of the two chunks, if technical > 0."""
    selected: bool = False
    rank: int = 0


def one_line(text: str) -> str:
    return " ".join(text.split())


def load_folder_documents(db, folder: Path) -> list[Document]:
    """The newest stored document (with chunks) for each .pdf filename in `folder`."""
    if not folder.is_dir():
        raise SystemExit(f"--folder: {folder} is not a directory")
    filenames = sorted(p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")
    if not filenames:
        raise SystemExit(f"--folder: no .pdf files in {folder}")

    newest: dict[str, Document] = {}
    for document in db.scalars(
        select(Document)
        .where(Document.filename.in_(filenames), Document.id.in_(select(Chunk.document_id)))
        .order_by(Document.uploaded_at, Document.id)
    ):
        newest[document.filename] = document
    missing = [name for name in filenames if name not in newest]
    if missing:
        raise SystemExit(f"These PDFs are not stored in the database (or have no chunks): "
                         f"{', '.join(missing)}")
    return [newest[name] for name in filenames]


def load_chunks(db, document_ids: list) -> list[Chunk]:
    """Chunks in the same order run_pipeline() uses, so tie-breaks and pair orientation match."""
    return list(
        db.scalars(
            select(Chunk)
            .options(joinedload(Chunk.document))
            .where(Chunk.document_id.in_(document_ids))
            .order_by(Chunk.document_id, Chunk.page_number, Chunk.id)
        )
    )


def fill_missing_in_memory(chunks: list[Chunk], entity_types: dict) -> tuple[int, int]:
    """Compute entity types / embeddings for chunks lacking them, without storing anything.

    The chunks must already be detached from their session.
    """
    no_entities = [c for c in chunks if c.id not in entity_types]
    for chunk, entities in zip(no_entities, extract_entities([c.text for c in no_entities])):
        if entities:
            entity_types[chunk.id] = {e.label for e in entities}
    no_embedding = [c for c in chunks if c.embedding is None]
    for chunk, vector in zip(no_embedding, embed_texts([c.text for c in no_embedding])):
        chunk.embedding = vector
    return len(no_entities), len(no_embedding)


def score_all_pairs(chunks: list[Chunk], entity_types: dict) -> list[ScoredPair]:
    embedding_sim = embedding_similarity_matrix(chunks)
    tfidf_sim = tfidf_similarity_matrix([chunk.text for chunk in chunks])
    claims = [extract_technical_claims(chunk.text) for chunk in chunks]
    pairs = []
    for i in range(len(chunks)):
        for j in range(i + 1, len(chunks)):
            if chunks[i].document_id == chunks[j].document_id:
                continue
            tfidf = float(tfidf_sim[i, j])
            embedding = float(embedding_sim[i, j])
            overlap = entity_overlap(
                entity_types.get(chunks[i].id, set()), entity_types.get(chunks[j].id, set())
            )
            technical = technical_compatibility(claims[i], claims[j])
            combined = combined_score(tfidf, embedding, overlap, technical)
            pair = ScoredPair(i, j, tfidf, embedding, overlap, technical, combined)
            if technical:
                a, b = max(((a, b) for a in claims[i] for b in claims[j]),
                           key=lambda ab: claim_compatibility(*ab))
                pair.claim_a, pair.claim_b = one_line(a.text), one_line(b.text)
            pairs.append(pair)

    pairs.sort(key=lambda p: (-p.combined, p.i, p.j))
    for rank, pair in enumerate(pairs, start=1):
        pair.rank = rank
    return pairs


def check_all_scored(pairs: list[ScoredPair], chunks: list[Chunk], entity_types: dict) -> int:
    """Check that generate_candidates() scores every cross-document pair; return how many it scored.

    With a budget as large as the number of pairs nothing can be dropped by selection, so
    any pair missing from the result was filtered out before combined scoring.
    """
    selection = generate_candidates(chunks, entity_types, max_candidates=len(pairs))
    assert selection.cross_document_pairs == len(pairs), "cross-document pair count differs"
    assert selection.scored_pairs == len(pairs), "some pairs did not reach combined scoring"
    by_ids = {frozenset((chunks[p.i].id, chunks[p.j].id)): p for p in pairs}
    returned = {frozenset((c.chunk_a.id, c.chunk_b.id)): c for c in selection.candidates}
    assert returned.keys() == by_ids.keys(), "production did not return every cross-document pair"
    for key, candidate in returned.items():
        assert abs(by_ids[key].combined - candidate.combined_score) < 1e-9, (
            "diagnostic score differs from production"
        )
    return selection.scored_pairs


def mark_selected(pairs: list[ScoredPair], chunks: list[Chunk], entity_types: dict) -> int:
    """Run generate_candidates() with the real budget and flag the pairs it keeps."""
    selection = generate_candidates(chunks, entity_types)
    by_ids = {frozenset((chunks[p.i].id, chunks[p.j].id)): p for p in pairs}
    for candidate in selection.candidates:
        pair = by_ids[frozenset((candidate.chunk_a.id, candidate.chunk_b.id))]
        assert abs(pair.combined - candidate.combined_score) < 1e-9, "diagnostic score differs from production"
        pair.selected = True
    return len(selection.candidates)


def write_csv(path: Path, pairs: list[ScoredPair], chunks: list[Chunk], entity_types: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "rank", "document_a", "page_a", "chunk_id_a", "document_b", "page_b", "chunk_id_b",
            "tfidf_similarity", "embedding_similarity", "entity_overlap",
            "technical_compatibility", "combined_score", "selected",
            "technical_claim_a", "technical_claim_b", "entity_types_a", "entity_types_b",
            "text_a", "text_b",
        ])
        for p in pairs:
            a, b = chunks[p.i], chunks[p.j]
            writer.writerow([
                p.rank, a.document.filename, a.page_number, a.id,
                b.document.filename, b.page_number, b.id,
                f"{p.tfidf:.6f}", f"{p.embedding:.6f}", f"{p.entity:.6f}",
                f"{p.technical:.6f}", f"{p.combined:.6f}", int(p.selected),
                p.claim_a, p.claim_b,
                "|".join(sorted(entity_types.get(a.id, set()))),
                "|".join(sorted(entity_types.get(b.id, set()))),
                one_line(a.text), one_line(b.text),
            ])


def flags(p: ScoredPair) -> str:
    return "SELECTED" if p.selected else "not selected"


def print_pair(p: ScoredPair, chunks: list[Chunk], preview: int) -> None:
    a, b = chunks[p.i], chunks[p.j]
    print(f"\n{'-' * TEXT_WIDTH}")
    print(f"#{p.rank:<4} combined {p.combined:.3f}  tfidf {p.tfidf:.3f}  embedding {p.embedding:.3f}  "
          f"entity {p.entity:.3f}  technical {p.technical:.3f}  [{flags(p)}]")
    if p.technical:
        print(f"  technical claims: {p.claim_a!r} <-> {p.claim_b!r}")
    for label, chunk in (("A", a), ("B", b)):
        text = one_line(chunk.text)
        if preview and len(text) > preview:
            text = text[:preview] + " ..."
        print(f"  [{label}] {chunk.document.filename} p{chunk.page_number}  chunk {chunk.id}")
        print(textwrap.fill(text, width=TEXT_WIDTH, initial_indent="      ", subsequent_indent="      "))


def find_pairs(pairs: list[ScoredPair], chunks: list[Chunk], term_a: str, term_b: str) -> None:
    ta, tb = one_line(term_a).lower(), one_line(term_b).lower()
    hits = []
    for p in pairs:
        x, y = one_line(chunks[p.i].text).lower(), one_line(chunks[p.j].text).lower()
        if (ta in x and tb in y) or (tb in x and ta in y):
            hits.append(p)
    print(f"\n--find {term_a!r} <-> {term_b!r}: {len(hits)} cross-document pairs")
    for p in hits:
        a, b = chunks[p.i], chunks[p.j]
        print(f"  rank {p.rank:>4}/{len(pairs)}  combined {p.combined:.3f}  "
              f"(tfidf {p.tfidf:.3f} emb {p.embedding:.3f} ent {p.entity:.3f} tech {p.technical:.3f})  "
              f"{a.document.filename} p{a.page_number} <-> {b.document.filename} p{b.page_number}  "
              f"[{flags(p)}]")
        if p.technical:
            print(f"      technical claims: {p.claim_a!r} <-> {p.claim_b!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Score every cross-document chunk pair before filtering.")
    parser.add_argument("--folder", type=Path, default=DEFAULT_FOLDER)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--top", type=int, default=30, help="pairs to print")
    parser.add_argument("--preview", type=int, default=400,
                        help="characters of each chunk to print (0 = full text)")
    parser.add_argument("--find", nargs=2, action="append", default=[], metavar=("TEXT_A", "TEXT_B"))
    args = parser.parse_args()
    sys.stdout.reconfigure(errors="replace")

    with SessionLocal() as db:
        documents = load_folder_documents(db, args.folder.resolve())
        chunks = load_chunks(db, [d.id for d in documents])
        entity_types = load_entity_types(db, [c.id for c in chunks])
        db.expunge_all()

    computed_entities, computed_embeddings = fill_missing_in_memory(chunks, entity_types)

    print(f"Folder: {args.folder.resolve()}")
    per_document = Counter(c.document.filename for c in chunks)
    for d in documents:
        print(f"  {d.filename:<8} {per_document[d.filename]:>3} chunks  {d.id}")
    if computed_entities or computed_embeddings:
        print(f"  (computed in memory, not stored: NER for {computed_entities} chunks, "
              f"embeddings for {computed_embeddings} chunks)")

    names = [d.filename for d in documents]
    possible = sum(per_document[a] * per_document[b]
                   for n, a in enumerate(names) for b in names[n + 1:])

    pairs = score_all_pairs(chunks, entity_types)
    scored_by_production = check_all_scored(pairs, chunks, entity_types)
    selected = mark_selected(pairs, chunks, entity_types)
    write_csv(args.output, pairs, chunks, entity_types)

    print(f"\ncombined = {1 - W_TECHNICAL:.2f} x ({W_TFIDF} x TF-IDF + {W_EMBEDDING} x embedding "
          f"+ {W_ENTITY} x entity-type overlap) + {W_TECHNICAL} x technical compatibility")
    print(f"Pairs with technical compatibility > 0:    {sum(p.technical > 0 for p in pairs)}")
    print(f"Total chunks:                              {len(chunks)}")
    print(f"Possible cross-document pairs:             {possible}")
    print(f"Pairs scored by this diagnostic:           {len(pairs)}")
    print(f"Pairs scored by generate_candidates():     {scored_by_production}")
    print(f"Pairs selected by generate_candidates():   {selected} (MAX_CANDIDATES = {MAX_CANDIDATES})")
    print(f"Selected pairs within the top {selected} ranks:     {sum(p.selected for p in pairs[:selected])}")
    if selected:
        worst = max(p.rank for p in pairs if p.selected)
        print(f"Lowest-ranked selected pair:               rank {worst}")
        print(f"Unselected pairs ranked above it:          {sum(not p.selected for p in pairs[:worst])}")
    print(f"Top-{args.top} by combined score: {sum(p.selected for p in pairs[:args.top])} selected")

    print("\nPairs per document pair (all / selected):")
    by_document_pair = Counter()
    for p in pairs:
        key = tuple(sorted((chunks[p.i].document.filename, chunks[p.j].document.filename)))
        by_document_pair[key, "all"] += 1
        by_document_pair[key, "sel"] += p.selected
    for n, a in enumerate(names):
        for b in names[n + 1:]:
            print(f"  {a}-{b}: {by_document_pair[(a, b), 'all']:>4} / {by_document_pair[(a, b), 'sel']:>3}")

    print(f"\nFull ranked list written to {args.output.resolve()}")

    print(f"\n=== Top {min(args.top, len(pairs))} of {len(pairs)} pairs by combined score ===")
    for p in pairs[:args.top]:
        print_pair(p, chunks, args.preview)
    print("-" * TEXT_WIDTH)

    for term_a, term_b in args.find:
        find_pairs(pairs, chunks, term_a, term_b)


if __name__ == "__main__":
    main()
