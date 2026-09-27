import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.services.claude_analysis import Evidence


class ChunkSource(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID | None
    filename: str | None
    title: str | None
    section: str | None
    page_number: int | None
    text: str


class AnalysisResult(BaseModel):
    id: uuid.UUID
    verdict: Literal["CONTRADICTION", "CONSISTENT", "UNCERTAIN"] | None
    topic: str | None
    reasoning: str | None
    confidence: float | None
    evidence: list[Evidence] | None
    candidate_pair_id: uuid.UUID | None
    method: str | None
    statement_a: ChunkSource | None
    statement_b: ChunkSource | None
    created_at: datetime | None
