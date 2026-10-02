import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.services.claude_analysis import Evidence


class DocumentInfo(BaseModel):
    id: uuid.UUID
    filename: str
    title: str | None
    doc_type: str | None
    uploaded_at: datetime | None
    chunk_count: int


class UploadedDocument(DocumentInfo):
    page_count: int
    """Pages with extractable text."""


class AnalysisRunRequest(BaseModel):
    document_ids: list[uuid.UUID] = Field(min_length=2)


class AnalysisRunSummary(BaseModel):
    document_ids: list[uuid.UUID]
    documents: int
    chunks: int
    candidates_processed: int
    results_stored: int
    skipped_existing: int
    errors: int


class ChunkSource(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID | None
    filename: str | None
    title: str | None
    doc_type: str | None
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
    # A statement is a whole chunk: these are the two chunks that were sent to Claude.
    statement_a: ChunkSource | None
    statement_b: ChunkSource | None
    created_at: datetime | None
