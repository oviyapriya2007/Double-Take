import uuid

from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased, joinedload

from app.models import CandidatePair, Chunk, ContradictionResult
from app.services.claude_analysis import ContradictionVerdict


def get_or_create_candidate_pair(
    db: Session,
    chunk_a_id: uuid.UUID,
    chunk_b_id: uuid.UUID,
    method: str,
) -> CandidatePair:
    """Return the existing pair for these two chunks and method, or add a new one.

    The caller is responsible for committing.
    """
    pair = db.scalars(
        select(CandidatePair).where(
            CandidatePair.chunk_a_id == chunk_a_id,
            CandidatePair.chunk_b_id == chunk_b_id,
            CandidatePair.method == method,
        )
    ).first()
    if pair is None:
        pair = CandidatePair(chunk_a_id=chunk_a_id, chunk_b_id=chunk_b_id, method=method)
        db.add(pair)
        db.flush()
    return pair


def store_contradiction_result(
    db: Session,
    candidate_pair_id: uuid.UUID,
    result: ContradictionVerdict,
    llm_raw_response: dict | None = None,
) -> ContradictionResult:
    """Add a contradiction_results row for one validated Claude finding and flush.

    The caller is responsible for committing.
    """
    row = ContradictionResult(
        candidate_pair_id=candidate_pair_id,
        verdict=result.verdict,
        topic=result.topic,
        reasoning=result.reasoning,
        evidence=[item.model_dump() for item in result.evidence],
        confidence=result.confidence,
        llm_raw_response=llm_raw_response,
    )
    db.add(row)
    db.flush()
    return row


def _select_results_with_sources():
    """Select results with their pair, chunks and documents loaded in the same query."""
    pair = joinedload(ContradictionResult.candidate_pair)
    return select(ContradictionResult).options(
        pair.joinedload(CandidatePair.chunk_a).joinedload(Chunk.document),
        pair.joinedload(CandidatePair.chunk_b).joinedload(Chunk.document),
    )


def list_contradiction_results(
    db: Session, document_ids: Collection[uuid.UUID] | None = None
) -> list[ContradictionResult]:
    """Stored results, newest first, with their pair, chunks and documents loaded.

    With document_ids, only results whose two chunks both belong to those documents.
    """
    query = _select_results_with_sources()
    if document_ids is not None:
        chunk_a, chunk_b = aliased(Chunk), aliased(Chunk)
        pairs_within = (
            select(CandidatePair.id)
            .join(chunk_a, CandidatePair.chunk_a_id == chunk_a.id)
            .join(chunk_b, CandidatePair.chunk_b_id == chunk_b.id)
            .where(chunk_a.document_id.in_(document_ids), chunk_b.document_id.in_(document_ids))
        )
        query = query.where(ContradictionResult.candidate_pair_id.in_(pairs_within))
    return list(db.scalars(query.order_by(ContradictionResult.created_at.desc())).unique())


def get_contradiction_result(db: Session, result_id: uuid.UUID) -> ContradictionResult | None:
    """One stored result with its pair, chunks and documents loaded, or None."""
    return db.scalars(
        _select_results_with_sources().where(ContradictionResult.id == result_id)
    ).unique().first()
