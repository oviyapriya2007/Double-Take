from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CandidatePair, ContradictionResult
from app.retrieval.candidates import CANDIDATE_METHOD, Candidate


def store_candidates(
    db: Session, candidates: list[Candidate], method: str = CANDIDATE_METHOD
) -> list[CandidatePair]:
    """Make candidate_pairs hold exactly these candidates for `method`, one row per chunk pair.

    - A pair that already has a row (in either chunk order) keeps that row; only its scores
      are updated, so rerunning never creates duplicates.
    - Rows of `method` from earlier runs that are no longer selected are deleted, unless a
      contradiction result already refers to them.
    - Rows of other methods (e.g. the Day 1 "manual" pair) are not touched.

    The caller is responsible for committing.
    """
    existing: dict[frozenset, CandidatePair] = {}
    stale: list[CandidatePair] = []
    for row in db.scalars(select(CandidatePair).where(CandidatePair.method == method)):
        key = frozenset((row.chunk_a_id, row.chunk_b_id))
        if key in existing:
            stale.append(row)
        else:
            existing[key] = row

    stored = []
    for candidate in candidates:
        row = existing.pop(frozenset((candidate.chunk_a.id, candidate.chunk_b.id)), None)
        if row is None:
            row = CandidatePair(
                chunk_a_id=candidate.chunk_a.id, chunk_b_id=candidate.chunk_b.id, method=method
            )
            db.add(row)
        row.tfidf_score = candidate.tfidf_score
        row.embedding_score = candidate.embedding_score
        row.entity_overlap_score = candidate.entity_overlap
        row.combined_score = candidate.combined_score
        stored.append(row)

    stale.extend(existing.values())
    if stale:
        referenced = set(
            db.scalars(
                select(ContradictionResult.candidate_pair_id).where(
                    ContradictionResult.candidate_pair_id.in_([row.id for row in stale])
                )
            )
        )
        for row in stale:
            if row.id not in referenced:
                db.delete(row)

    db.flush()
    return stored
