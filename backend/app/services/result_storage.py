import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

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
    """Add a contradiction_results row for a validated Claude verdict and flush.

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


def list_contradiction_results(db: Session) -> list[ContradictionResult]:
    """All stored results, newest first, with their pair, chunks and documents loaded."""
    pair = joinedload(ContradictionResult.candidate_pair)
    return list(
        db.scalars(
            select(ContradictionResult)
            .options(
                pair.joinedload(CandidatePair.chunk_a).joinedload(Chunk.document),
                pair.joinedload(CandidatePair.chunk_b).joinedload(Chunk.document),
            )
            .order_by(ContradictionResult.created_at.desc())
        ).unique()
    )
