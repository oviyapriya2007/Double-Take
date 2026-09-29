"""Temporary Day 3 check: run run_pipeline() end to end on a few candidate pairs only.

    python scripts/verify_pipeline.py
    python scripts/verify_pipeline.py --limit 5
    python scripts/verify_pipeline.py --folder ../data/some_folder --limit 10

With --folder, only the stored documents whose filename matches a .pdf in that folder are
used (the newest stored copy of each); nothing is imported. Without it, every stored
document is used. Note that the pipeline's candidate storage then holds candidates for
those documents only, as it would in production.

Runs the pipeline on the chosen documents, but only the first --limit existing "combined"
candidate pairs (highest combined score) are analysed, and Claude is called at most --limit
times. Candidate storage itself still runs on the full selection, exactly as in production.
Pairs that already have a result are skipped by the pipeline, so a rerun calls Claude
for none of them. Prints the PipelineSummary and the contradiction results stored by this run.
"""

import argparse
import dataclasses
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import CandidatePair, Chunk, ContradictionResult, Document  # noqa: E402
from app.retrieval.candidates import CANDIDATE_METHOD  # noqa: E402
from app.services import pipeline  # noqa: E402
from app.services.result_storage import list_contradiction_results  # noqa: E402


def load_documents(db) -> list[Document]:
    """Every stored document that has at least one chunk."""
    return list(
        db.scalars(
            select(Document)
            .where(Document.id.in_(select(Chunk.document_id)))
            .order_by(Document.filename)
        )
    )


def load_folder_documents(db, folder: Path) -> list[Document]:
    """The stored documents (with chunks) matching the .pdf files in `folder` by filename.

    If a filename was stored more than once, the newest copy is used. Stops with an error if
    the folder has no PDFs or any of its PDFs is not stored.
    """
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
        raise SystemExit(
            f"--folder: these PDFs in {folder} are not stored in the database (or have no chunks): "
            f"{', '.join(missing)}\nLoad each one first with scripts/verify_chunk_storage.py <pdf>."
        )
    return [newest[name] for name in filenames]


def select_pairs(db, document_ids: list, limit: int) -> list[CandidatePair]:
    """The first `limit` stored combined pairs whose chunks both belong to these documents."""
    in_documents = select(Chunk.id).where(Chunk.document_id.in_(document_ids))
    return list(
        db.scalars(
            select(CandidatePair)
            .where(
                CandidatePair.method == CANDIDATE_METHOD,
                CandidatePair.chunk_a_id.in_(in_documents),
                CandidatePair.chunk_b_id.in_(in_documents),
            )
            .order_by(CandidatePair.combined_score.desc(), CandidatePair.id)
            .limit(limit)
        )
    )


def limit_pipeline(selected_ids: set, limit: int) -> list[int]:
    """Restrict the pipeline module to the selected pairs and at most `limit` Claude calls.

    Returns a one-element list holding the number of Claude analyses performed.
    """
    real_store_candidates = pipeline.store_candidates
    real_compare = pipeline.compare_statements_with_raw
    calls = [0]

    def store_selected(db, candidates):
        return [pair for pair in real_store_candidates(db, candidates) if pair.id in selected_ids]

    def compare_capped(a, b):
        if calls[0] >= limit:
            raise RuntimeError(f"verification limit of {limit} Claude analyses reached")
        calls[0] += 1
        return real_compare(a, b)

    pipeline.store_candidates = store_selected
    pipeline.compare_statements_with_raw = compare_capped
    return calls


def one_line(text: str) -> str:
    return " ".join(text.split())


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the pipeline on a few candidate pairs.")
    parser.add_argument("--limit", type=int, default=3, help="candidate pairs to analyse")
    parser.add_argument("--folder", type=Path,
                        help="use only the stored documents matching the PDFs in this folder")
    args = parser.parse_args()
    if args.limit < 1:
        raise SystemExit("--limit must be at least 1")
    sys.stdout.reconfigure(errors="replace")
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    with SessionLocal() as db:
        if args.folder:
            folder = args.folder.resolve()
            documents = load_folder_documents(db, folder)
            print(f"Folder: {folder}")
        else:
            documents = load_documents(db)
        document_ids = [document.id for document in documents]
        print(f"Documents ({len(documents)}):")
        for document in documents:
            print(f"  {document.filename:<20} {document.id}")

        pairs = select_pairs(db, document_ids, args.limit)
        if not pairs:
            raise SystemExit("No stored combined candidate pairs. Run scripts/verify_candidates.py first.")
        analysed = set(db.scalars(
            select(ContradictionResult.candidate_pair_id)
            .where(ContradictionResult.candidate_pair_id.in_([pair.id for pair in pairs]))
        ))
        print(f"\nSelected {len(pairs)} candidate pairs (--limit {args.limit}):")
        for pair in pairs:
            status = "already has a result, will be skipped" if pair.id in analysed else "new"
            print(f"  {pair.id}  combined {pair.combined_score:.3f}  ({status})")
        selected_ids = {pair.id for pair in pairs}
        results_before = set(db.scalars(select(ContradictionResult.id)))

    calls = limit_pipeline(selected_ids, args.limit)
    with SessionLocal() as db:
        summary = pipeline.run_pipeline(db, document_ids)

    print("\nPipelineSummary:")
    for field, value in dataclasses.asdict(summary).items():
        print(f"  {field:<22}{value}")
    print(f"  {'claude_analyses':<22}{calls[0]}")

    with SessionLocal() as db:
        new_results = [row for row in list_contradiction_results(db) if row.id not in results_before]

    print(f"\nContradiction results stored by this run: {len(new_results)}")
    for row in new_results:
        pair = row.candidate_pair
        print(f"\n{row.verdict}  confidence {row.confidence}  topic: {row.topic}")
        print(f"  pair {pair.id}: {pair.chunk_a.document.filename} p{pair.chunk_a.page_number}"
              f"  <->  {pair.chunk_b.document.filename} p{pair.chunk_b.page_number}")
        print(f"  reasoning: {one_line(row.reasoning or '')}")
        print(f"  evidence: {json.dumps(row.evidence, indent=2, ensure_ascii=False)}")

    assert calls[0] <= args.limit, "more Claude analyses than --limit"
    assert summary.candidates_processed <= args.limit, "more candidate pairs processed than --limit"
    assert summary.results_stored == len(new_results), "summary does not match the stored results"
    print(f"\nOK: {summary.candidates_processed} candidate pairs processed, {calls[0]} Claude analyses, "
          f"{len(new_results)} results stored, {summary.skipped_existing} skipped, {summary.errors} errors")


if __name__ == "__main__":
    main()
