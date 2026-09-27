from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Chunk, ContradictionResult
from app.schemas import AnalysisResult, ChunkSource
from app.services.result_storage import list_contradiction_results

app = FastAPI(title="Double-Take")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _chunk_source(chunk: Chunk | None) -> ChunkSource | None:
    if chunk is None:
        return None
    document = chunk.document
    return ChunkSource(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        filename=document.filename if document else None,
        title=document.title if document else None,
        section=chunk.section,
        page_number=chunk.page_number,
        text=chunk.text,
    )


def _analysis_result(row: ContradictionResult) -> AnalysisResult:
    pair = row.candidate_pair
    return AnalysisResult(
        id=row.id,
        verdict=row.verdict,
        topic=row.topic,
        reasoning=row.reasoning,
        confidence=row.confidence,
        evidence=row.evidence,
        candidate_pair_id=row.candidate_pair_id,
        method=pair.method if pair else None,
        statement_a=_chunk_source(pair.chunk_a if pair else None),
        statement_b=_chunk_source(pair.chunk_b if pair else None),
        created_at=row.created_at,
    )


@app.get("/analysis/results", response_model=list[AnalysisResult])
def get_analysis_results(db: Session = Depends(get_db)) -> list[AnalysisResult]:
    return [_analysis_result(row) for row in list_contradiction_results(db)]
