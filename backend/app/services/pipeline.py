"""Automatic contradiction analysis over a set of stored documents.

documents -> chunks -> NER / embeddings -> candidate pairs -> retrieval -> Claude -> results

Every step reuses an existing service; this module only orchestrates them.
"""

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass

from langchain_core.documents import Document as LangChainDocument
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import CandidatePair, Chunk, ContradictionResult, Document, Entity
from app.retrieval.candidates import generate_candidates
from app.retrieval.retriever import CrossDocumentRetriever
from app.services.candidate_storage import store_candidates
from app.services.claude_analysis import Statement, compare_statements_with_raw
from app.services.embedding_storage import embed_and_store_chunks
from app.services.entity_storage import extract_and_store_entities, load_entity_types
from app.services.result_storage import store_contradiction_result

logger = logging.getLogger(__name__)

EntityMap = dict[uuid.UUID, list[tuple[str, str]]]


@dataclass
class PipelineSummary:
    documents: int
    chunks: int
    candidates_processed: int = 0
    results_stored: int = 0
    skipped_existing: int = 0
    """Candidate pairs that already had a stored result, so Claude was not called again."""
    errors: int = 0
    """Candidate pairs skipped because retrieval, Claude, validation or storage failed."""


def run_pipeline(db: Session, document_ids: list[uuid.UUID]) -> PipelineSummary:
    """Analyse the given documents for contradictions and store the results.

    Commits after preparing chunks and candidate pairs, and again after each stored result,
    so a rerun skips pairs that were already analysed. A failure on one candidate pair is
    logged, rolled back and counted in `errors`; the remaining pairs are still processed.

    Raises ValueError if a document id is unknown or fewer than two of the documents have
    chunks.
    """
    chunks = _load_chunks(db, document_ids)
    _ensure_entities_and_embeddings(db, chunks)
    entity_types = load_entity_types(db, [chunk.id for chunk in chunks])
    pairs = store_candidates(db, generate_candidates(chunks, entity_types).candidates)
    db.commit()

    chunk_by_id = {chunk.id: chunk for chunk in chunks}
    entities = _load_entities(db, list(chunk_by_id))
    analysed = _pairs_with_results(db, pairs)
    retriever = CrossDocumentRetriever(db=db)
    summary = PipelineSummary(
        documents=len({chunk.document_id for chunk in chunks}), chunks=len(chunks)
    )

    for pair in pairs:
        pair_id = pair.id
        summary.candidates_processed += 1
        if pair_id in analysed:
            summary.skipped_existing += 1
            continue
        try:
            chunk_a, chunk_b = chunk_by_id[pair.chunk_a_id], chunk_by_id[pair.chunk_b_id]
            context = retriever.retrieve_for_chunk(chunk_a)
            a = _statement(chunk_a, entities)
            b = _statement_from_context(chunk_b, context, entities)
            result, raw_response = compare_statements_with_raw(a, b)
            store_contradiction_result(db, pair_id, result, raw_response)
            db.commit()
            summary.results_stored += 1
        except Exception:
            db.rollback()
            summary.errors += 1
            logger.exception("Skipping candidate pair %s", pair_id)

    return summary


def _load_chunks(db: Session, document_ids: list[uuid.UUID]) -> list[Chunk]:
    """The chunks of the requested documents, with their document loaded, in a fixed order."""
    unique_ids = list(dict.fromkeys(document_ids))
    found = set(db.scalars(select(Document.id).where(Document.id.in_(unique_ids))))
    missing = [str(document_id) for document_id in unique_ids if document_id not in found]
    if missing:
        raise ValueError(f"Unknown document ids: {', '.join(missing)}")

    chunks = list(
        db.scalars(
            select(Chunk)
            .options(joinedload(Chunk.document))
            .where(Chunk.document_id.in_(unique_ids))
            .order_by(Chunk.document_id, Chunk.page_number, Chunk.id)
        )
    )
    if len({chunk.document_id for chunk in chunks}) < 2:
        raise ValueError("At least two of the documents must have chunks to compare")
    return chunks


def _ensure_entities_and_embeddings(db: Session, chunks: list[Chunk]) -> None:
    """Run NER on chunks with no stored entities and embed chunks with no stored embedding.

    A chunk in which NER genuinely finds nothing is re-run on every call; this is harmless
    because extract_and_store_entities replaces a chunk's entities rather than adding to them.
    """
    with_entities = load_entity_types(db, [chunk.id for chunk in chunks])
    without_entities = [chunk for chunk in chunks if chunk.id not in with_entities]
    if without_entities:
        extract_and_store_entities(db, without_entities)

    without_embedding = [chunk for chunk in chunks if chunk.embedding is None]
    if without_embedding:
        embed_and_store_chunks(db, without_embedding)


def _load_entities(db: Session, chunk_ids: list[uuid.UUID]) -> EntityMap:
    """(entity_type, entity_text) pairs stored for each chunk, in text order."""
    entities: EntityMap = defaultdict(list)
    rows = db.execute(
        select(Entity.chunk_id, Entity.entity_type, Entity.entity_text)
        .where(
            Entity.chunk_id.in_(chunk_ids),
            Entity.entity_type.is_not(None),
            Entity.entity_text.is_not(None),
        )
        .order_by(Entity.chunk_id, Entity.start_char)
    )
    for chunk_id, entity_type, entity_text in rows:
        entities[chunk_id].append((entity_type, entity_text))
    return entities


def _pairs_with_results(db: Session, pairs: list[CandidatePair]) -> set[uuid.UUID]:
    """Ids of the candidate pairs that already have a contradiction result."""
    if not pairs:
        return set()
    return set(
        db.scalars(
            select(ContradictionResult.candidate_pair_id).where(
                ContradictionResult.candidate_pair_id.in_([pair.id for pair in pairs])
            )
        )
    )


def _statement(chunk: Chunk, entities: EntityMap) -> Statement:
    """Claude statement for a stored chunk: its text, document/page/section and entities."""
    return Statement(
        text=chunk.text,
        document=chunk.document.filename,
        page=chunk.page_number,
        section=chunk.section,
        entities=entities.get(chunk.id, []),
    )


def _statement_from_context(
    chunk: Chunk, context: list[LangChainDocument], entities: EntityMap
) -> Statement:
    """Claude statement for the cross-document chunk, built from the retrieved context.

    Falls back to the stored chunk when the retriever's top results do not include it.
    """
    retrieved = next((doc for doc in context if doc.metadata["chunk_id"] == str(chunk.id)), None)
    if retrieved is None:
        logger.debug("Chunk %s not among the retrieved context; using the stored chunk", chunk.id)
        return _statement(chunk, entities)
    return Statement(
        text=retrieved.page_content,
        document=retrieved.metadata["filename"],
        page=retrieved.metadata["page_number"],
        section=retrieved.metadata["section"],
        entities=entities.get(chunk.id, []),
    )
