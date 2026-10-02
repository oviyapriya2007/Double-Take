"""Candidate score distribution for one or more PDF folders (Fix #5 diagnostic).

    python scripts/diagnose_score_distribution.py
    python scripts/diagnose_score_distribution.py "../data/test data" ../data/sample_docs ../data/sample_docs/test_ei
    python scripts/diagnose_score_distribution.py FOLDER --labels topics.json --all-pairs --show 10

Fully in memory: each PDF is extracted and chunked with the production ingestion helpers,
NER and embeddings come from the production models, and every cross-document pair is
scored by generate_candidates() itself, with no score floor, no per-document-pair limit
and a budget large enough to keep every pair.
Nothing is read from or written to the database. A second generate_candidates() call with
the real budget only marks which pairs production would select. Chunks are referred to as
"<file> p<page> c<n>", n being the chunk's position in its document (stable across runs).

Known related pairs come from an optional labels file, by default related_topics.json in
the folder:

    {"topics": {"flow rate": ["maintain the process flow rate"],
                "maximum pressure": {"a": "Maximum System Operating Pressure",
                                     "b": "Fluid System Maximum Pressure Rating"}}}

A list of phrases relates a pair when both chunks contain one of them; {"a": ..., "b": ...}
(a phrase or a list of phrases on each side) relates a pair when one chunk contains an "a"
phrase and the other a "b" phrase, like diagnose_candidates.py --find. Case and whitespace
are ignored. With labels, pairs related to no topic are the unrelated pairs, so the labels
should cover every claim the documents share. Without labels, related and unrelated pairs
are reported as not identifiable.
"""

import argparse
import json
import math
import statistics
import sys
import uuid
from collections import Counter
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models import Chunk, Document  # noqa: E402
from app.nlp.embeddings import embed_texts  # noqa: E402
from app.nlp.ner import extract_entities  # noqa: E402
from app.retrieval import candidates as production  # noqa: E402
from app.retrieval.candidates import (  # noqa: E402
    MAX_CANDIDATES,
    W_EMBEDDING,
    W_ENTITY,
    W_TECHNICAL,
    W_TFIDF,
    Candidate,
    generate_candidates,
)
from app.services.chunking import chunk_pages  # noqa: E402
from app.services.pdf_extraction import extract_pages  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FOLDER = PROJECT_ROOT / "data" / "test data"
LABELS_FILENAME = "related_topics.json"
DEFAULT_THRESHOLDS = [0.2, 0.3, 0.4, 0.5, 0.6]
HISTOGRAM_WIDTH = 50
HEADER = (f"{'rank':>5}  {'combined':>8}  {'tfidf':>6}  {'embed':>6}  {'entity':>6}  {'tech':>6}  "
          f"{'sel':<3}  pair")


Topics = dict[str, tuple[list[str], list[str]]]
"""Topic -> (phrases one chunk must contain, phrases the other chunk must contain)."""


@dataclass
class Dataset:
    folder: Path
    labels: Path | None
    documents: list[tuple[str, int, int]]
    """(filename, pages with text, chunks) per PDF."""
    chunk_ref: dict[uuid.UUID, str]
    ranked: list[tuple[int, Candidate]]
    selected: set[frozenset]
    topics: Topics | None
    related: list[tuple[int, Candidate]] = field(default_factory=list)
    unrelated: list[tuple[int, Candidate]] = field(default_factory=list)


def normalized(text: str) -> str:
    return " ".join(text.split()).lower()


def pair_key(c: Candidate) -> frozenset:
    return frozenset((c.chunk_a.id, c.chunk_b.id))


def load_topics(path: Path) -> Topics:
    data = json.loads(path.read_text(encoding="utf-8"))
    topics = data.get("topics") if isinstance(data, dict) else None
    if not isinstance(topics, dict) or not topics:
        raise SystemExit(f'{path}: expected {{"topics": {{"<topic>": ..., ...}}}}')
    parsed: Topics = {}
    for topic, value in topics.items():
        sides = (value.get("a"), value.get("b")) if isinstance(value, dict) else (value, value)
        sides = [[side] if isinstance(side, str) else side for side in sides]
        if not all(isinstance(side, list) and side and all(isinstance(p, str) and p.strip() for p in side)
                   for side in sides):
            raise SystemExit(f'{path}: topic {topic!r} must be a list of phrases or '
                             f'{{"a": <phrase(s)>, "b": <phrase(s)>}}')
        parsed[topic] = ([normalized(p) for p in sides[0]], [normalized(p) for p in sides[1]])
    return parsed


def shared_topics(c: Candidate, topics: Topics | None) -> list[str]:
    if not topics:
        return []
    x, y = normalized(c.chunk_a.text), normalized(c.chunk_b.text)

    def contains(text: str, phrases: list[str]) -> bool:
        return any(p in text for p in phrases)

    return [topic for topic, (a, b) in topics.items()
            if (contains(x, a) and contains(y, b)) or (contains(x, b) and contains(y, a))]


def load_dataset(folder: Path, labels: Path | None) -> Dataset | None:
    """Chunk, embed and score the folder's PDFs; None (with a message) if it cannot be scored."""
    if not folder.is_dir():
        raise SystemExit(f"{folder} is not a directory")
    pdfs = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")
    chunks: list[Chunk] = []
    documents, chunk_ref = [], {}
    for path in pdfs:
        pages = extract_pages(path)
        document = Document(id=uuid.uuid4(), filename=path.name)
        pieces = chunk_pages(pages, document.id)
        documents.append((path.name, len(pages), len(pieces)))
        for n, piece in enumerate(pieces, start=1):
            chunk = Chunk(id=uuid.uuid4(), document_id=document.id, page_number=piece.page_number,
                          section=piece.section, text=piece.text)
            chunk.document = document
            chunk_ref[chunk.id] = f"{path.name} p{piece.page_number} c{n}"
            chunks.append(chunk)
    if sum(1 for _, _, count in documents if count) < 2:
        print(f"\nSkipping {folder}: fewer than two PDFs with extractable text.")
        return None

    texts = [chunk.text for chunk in chunks]
    entity_types = {
        chunk.id: {entity.label for entity in entities}
        for chunk, entities in zip(chunks, extract_entities(texts)) if entities
    }
    for chunk, vector in zip(chunks, embed_texts(texts)):
        chunk.embedding = vector

    unlimited = partial(production.select_with_document_coverage, max_per_document_pair=math.inf)
    with mock.patch.object(production, "select_with_document_coverage", unlimited):
        every = generate_candidates(
            chunks, entity_types, max_candidates=len(chunks) ** 2, min_score=-math.inf
        )
    assert len(every.candidates) == every.scored_pairs == every.cross_document_pairs, (
        "generate_candidates did not return every cross-document pair"
    )
    selected = {pair_key(c) for c in generate_candidates(chunks, entity_types).candidates}
    ranked = list(enumerate(sorted(every.candidates, key=lambda c: -c.combined_score), start=1))

    labels = labels or (folder / LABELS_FILENAME if (folder / LABELS_FILENAME).is_file() else None)
    topics = load_topics(labels) if labels else None
    dataset = Dataset(folder, labels, documents, chunk_ref, ranked, selected, topics)
    if topics:
        for row in ranked:
            (dataset.related if shared_topics(row[1], topics) else dataset.unrelated).append(row)
    return dataset


def print_rows(title: str, rows: list[tuple[int, Candidate]], d: Dataset) -> None:
    print(f"\n=== {title} ({len(rows)}) ===")
    if not rows:
        print("  (none)")
        return
    print(HEADER)
    for rank, c in rows:
        topics = shared_topics(c, d.topics)
        print(f"{rank:>5}  {c.combined_score:>8.3f}  {c.tfidf_score:>6.3f}  {c.embedding_score:>6.3f}  "
              f"{c.entity_overlap:>6.3f}  {c.technical_compatibility:>6.3f}  "
              f"{'yes' if pair_key(c) in d.selected else 'no':<3}  "
              f"{d.chunk_ref[c.chunk_a.id]}  <->  {d.chunk_ref[c.chunk_b.id]}"
              f"{'  [' + ', '.join(topics) + ']' if topics else ''}")


def separation(d: Dataset) -> tuple[float, float] | None:
    """(lowest related score, highest unrelated score), when both groups exist."""
    if not d.related or not d.unrelated:
        return None
    return min(c.combined_score for _, c in d.related), max(c.combined_score for _, c in d.unrelated)


def print_report(d: Dataset, args: argparse.Namespace) -> None:
    scores = [c.combined_score for _, c in d.ranked]
    print(f"\n{'#' * 100}\nFolder: {d.folder}")
    for filename, pages, count in d.documents:
        print(f"  {filename:<24} {pages:>3} pages  {count:>4} chunks")
    print(f"Labels: {d.labels if d.labels else f'none (no {LABELS_FILENAME} in the folder)'}")
    print(f"combined = {1 - W_TECHNICAL:.2f} x ({W_TFIDF} x TF-IDF + {W_EMBEDDING} x embedding "
          f"+ {W_ENTITY} x entity-type overlap) + {W_TECHNICAL} x technical compatibility")
    print(f"Cross-document pairs: {len(d.ranked)}   "
          f"selected by production: {len(d.selected)} (MAX_CANDIDATES = {MAX_CANDIDATES})")

    print("\n=== Combined score distribution ===")
    print(f"  min {min(scores):.3f}  max {max(scores):.3f}  mean {statistics.mean(scores):.3f}  "
          f"median {statistics.median(scores):.3f}")
    if len(scores) >= 2:
        q1, _, q3 = statistics.quantiles(scores, n=4)
        print(f"  Q1 {q1:.3f}  Q3 {q3:.3f}")
    buckets = Counter(min(int(score * 10), 9) for score in scores)
    largest = max(buckets.values())
    for bucket in range(9, -1, -1):
        count = buckets[bucket]
        bar = "#" * max(1, round(count * HISTOGRAM_WIDTH / largest)) if count else ""
        print(f"  {bucket / 10:.1f}-{(bucket + 1) / 10:.1f}  {count:>6}  {bar}")

    if args.all_pairs or len(d.ranked) <= args.list_limit:
        print_rows("All cross-document pairs, combined score descending", d.ranked, d)
    else:
        print(f"\n({len(d.ranked)} pairs; pass --all-pairs to list every one)")
    print_rows(f"Highest-scoring {args.show} pairs", d.ranked[:args.show], d)
    print_rows(f"Lowest-scoring {args.show} pairs", d.ranked[-args.show:], d)

    if d.topics is None:
        print("\n=== Known related pairs ===\n  not identifiable: no labels for this dataset")
        print("\n=== Unrelated sample ===\n  not identifiable: no labels for this dataset")
    else:
        print_rows("Known related pairs (both chunks state a labelled claim)", d.related, d)
        print_rows(f"Unrelated pairs, highest-scoring {args.sample} (no labelled claim in common)",
                   d.unrelated[:args.sample], d)

    print("\n=== Separation ===")
    sep = separation(d)
    if sep is None:
        print("  n/a: needs labelled related and unrelated pairs")
    else:
        lowest_related, highest_unrelated = sep
        print(f"  lowest related score:    {lowest_related:.3f}")
        print(f"  highest unrelated score: {highest_unrelated:.3f}")
        print(f"  separation (lowest related - highest unrelated): {lowest_related - highest_unrelated:+.3f}")

    print("\n=== Pairs at or above each threshold ===")
    for t in args.thresholds:
        line = f"  >= {t:.2f}: {sum(s >= t for s in scores):>6} of {len(scores)} pairs"
        if d.topics is not None:
            line += (f"   related kept {sum(c.combined_score >= t for _, c in d.related)}/{len(d.related)}"
                     f"   unrelated kept {sum(c.combined_score >= t for _, c in d.unrelated)}/{len(d.unrelated)}")
        print(line)


def print_comparison(datasets: list[Dataset], thresholds: list[float]) -> None:
    print(f"\n{'#' * 100}\n=== Comparison ===")
    print(f"{'folder':<28} {'pairs':>6} {'min':>6} {'median':>6} {'max':>6} "
          f"{'low rel':>7} {'high unr':>8} {'separ.':>7}  " + "  ".join(f">={t:.2f}" for t in thresholds))
    for d in datasets:
        scores = [c.combined_score for _, c in d.ranked]
        sep = separation(d)
        rel, unr, gap = (f"{sep[0]:.3f}", f"{sep[1]:.3f}", f"{sep[0] - sep[1]:+.3f}") if sep else ("-", "-", "-")
        kept = "  ".join(f"{sum(s >= t for s in scores):>6}" for t in thresholds)
        print(f"{d.folder.name[:28]:<28} {len(scores):>6} {min(scores):>6.3f} {statistics.median(scores):>6.3f} "
              f"{max(scores):>6.3f} {rel:>7} {unr:>8} {gap:>7}  {kept}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Candidate score distribution for PDF folders.")
    parser.add_argument("folders", nargs="*", type=Path, default=[DEFAULT_FOLDER],
                        help=f"PDF folders (default: {DEFAULT_FOLDER})")
    parser.add_argument("--labels", type=Path,
                        help=f"labels file for a single folder (default: <folder>/{LABELS_FILENAME})")
    parser.add_argument("--show", type=int, default=5, help="highest/lowest pairs to print")
    parser.add_argument("--sample", type=int, default=10, help="unrelated pairs to print")
    parser.add_argument("--all-pairs", action="store_true", help="list every pair, however many")
    parser.add_argument("--list-limit", type=int, default=60,
                        help="list every pair when there are at most this many")
    parser.add_argument("--thresholds", type=float, nargs="+", default=DEFAULT_THRESHOLDS)
    args = parser.parse_args()
    if args.labels and len(args.folders) > 1:
        raise SystemExit("--labels can only be used with a single folder")
    sys.stdout.reconfigure(errors="replace")

    datasets = [d for folder in args.folders
                if (d := load_dataset(folder.resolve(), args.labels)) is not None]
    for d in datasets:
        print_report(d, args)
    if len(datasets) > 1:
        print_comparison(datasets, args.thresholds)


if __name__ == "__main__":
    main()
