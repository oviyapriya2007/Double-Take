import dataclasses
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Chunk, ContradictionResult, Document
from app.schemas import (
    AnalysisResult,
    AnalysisRunRequest,
    AnalysisRunSummary,
    ChunkSource,
    DocumentInfo,
    UploadedDocument,
)
from app.services.document_ingestion import (
    IngestedDocument,
    IngestionError,
    ingest_uploaded_pdf,
    looks_like_pdf,
)
from app.services.pipeline import UnknownDocumentsError, run_pipeline
from app.services.result_storage import get_contradiction_result, list_contradiction_results

# The Vite dev server.
FRONTEND_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

app = FastAPI(title="Double-Take")
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _document_info(document: Document, chunk_count: int) -> DocumentInfo:
    return DocumentInfo(
        id=document.id,
        filename=document.filename,
        title=document.title,
        doc_type=document.doc_type,
        uploaded_at=document.uploaded_at,
        chunk_count=chunk_count,
    )


def _uploaded_document(ingested: IngestedDocument) -> UploadedDocument:
    info = _document_info(ingested.document, ingested.chunks)
    return UploadedDocument(**info.model_dump(), page_count=ingested.pages)


@app.post(
    "/documents/upload",
    response_model=list[UploadedDocument],
    status_code=status.HTTP_201_CREATED,
)
def upload_documents(
    # Swagger UI only renders a file picker for format: binary, not OpenAPI 3.1's contentMediaType.
    files: list[UploadFile] = File(
        ..., json_schema_extra={"items": {"type": "string", "format": "binary"}}
    ),
    doc_type: str | None = Form(None),
    db: Session = Depends(get_db),
) -> list[UploadedDocument]:
    """Store one or more text-based PDFs as documents with chunks; all or none are stored."""
    uploads = []
    for file in files:
        filename = Path(file.filename or "").name
        content = file.file.read()
        if not looks_like_pdf(filename, content):
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, f"{filename or 'Uploaded file'} is not a PDF"
            )
        uploads.append((filename, content))

    ingested: list[IngestedDocument] = []
    try:
        for filename, content in uploads:
            ingested.append(ingest_uploaded_pdf(db, filename, content, doc_type or None))
        db.commit()
    except BaseException as exc:
        db.rollback()
        for item in ingested:
            item.path.unlink(missing_ok=True)
        if isinstance(exc, IngestionError):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
        raise

    return [_uploaded_document(item) for item in ingested]


@app.get("/documents", response_model=list[DocumentInfo])
def get_documents(db: Session = Depends(get_db)) -> list[DocumentInfo]:
    """All stored documents, newest first."""
    chunk_count = func.count(Chunk.id)
    rows = db.execute(
        select(Document, chunk_count)
        .outerjoin(Chunk, Chunk.document_id == Document.id)
        .group_by(Document.id)
        .order_by(Document.uploaded_at.desc(), Document.id)
    )
    return [_document_info(document, count) for document, count in rows]


@app.post("/analysis/run", response_model=AnalysisRunSummary)
def run_analysis(request: AnalysisRunRequest, db: Session = Depends(get_db)) -> AnalysisRunSummary:
    """Run the contradiction pipeline on these documents and wait for it to finish."""
    document_ids = list(dict.fromkeys(request.document_ids))
    try:
        summary = run_pipeline(db, document_ids)
    except UnknownDocumentsError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return AnalysisRunSummary(document_ids=document_ids, **dataclasses.asdict(summary))


def _chunk_source(chunk: Chunk | None) -> ChunkSource | None:
    if chunk is None:
        return None
    document = chunk.document
    return ChunkSource(
        chunk_id=chunk.id,
        document_id=chunk.document_id,
        filename=document.filename if document else None,
        title=document.title if document else None,
        doc_type=document.doc_type if document else None,
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


def _parse_document_ids(value: str) -> list[uuid.UUID]:
    parts = [part.strip() for part in value.split(",") if part.strip()]
    if not parts:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "document_ids must contain at least one id"
        )
    try:
        return [uuid.UUID(part) for part in parts]
    except ValueError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"document_ids must be comma-separated UUIDs, got {value!r}",
        ) from exc


@app.get("/analysis/results", response_model=list[AnalysisResult])
def get_analysis_results(
    document_ids: str | None = Query(
        None,
        description="Comma-separated document ids. When given, only results comparing two of "
        "these documents are returned; when omitted, every stored result is returned.",
    ),
    db: Session = Depends(get_db),
) -> list[AnalysisResult]:
    ids = None if document_ids is None else _parse_document_ids(document_ids)
    return [_analysis_result(row) for row in list_contradiction_results(db, ids)]


@app.get("/analysis/results/{result_id}", response_model=AnalysisResult)
def get_analysis_result(result_id: uuid.UUID, db: Session = Depends(get_db)) -> AnalysisResult:
    row = get_contradiction_result(db, result_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis result not found")
    return _analysis_result(row)
