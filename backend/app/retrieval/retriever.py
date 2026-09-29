"""Single-hop RAG retrieval over chunks.embedding with pgvector.

Given a source chunk, returns the most similar chunks from other documents as LangChain
Documents: page_content is the chunk text, and metadata carries the document, section and
page. The similarity score is a retrieval signal only, never a contradiction verdict.
"""

import uuid

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document as LangChainDocument
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Chunk, Document
from app.nlp.embeddings import embed_texts

TOP_K = 5


def to_langchain_document(chunk: Chunk, document: Document, similarity: float) -> LangChainDocument:
    return LangChainDocument(
        page_content=chunk.text,
        metadata={
            "chunk_id": str(chunk.id),
            "document_id": str(document.id),
            "document_title": document.title,
            "filename": document.filename,
            "doc_type": document.doc_type,
            "section": chunk.section,
            "page_number": chunk.page_number,
            "similarity": similarity,
        },
    )


class CrossDocumentRetriever(BaseRetriever):
    """LangChain retriever over chunks.embedding that skips the chunks of one document.

    retrieve_for_chunk(chunk) searches with the chunk's stored embedding and excludes the
    chunk's own document. invoke(query_text) embeds the text with the project's embedding
    model and excludes exclude_document_id, if set.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    db: Session
    k: int = TOP_K
    exclude_document_id: uuid.UUID | None = None

    def retrieve_for_chunk(self, chunk: Chunk) -> list[LangChainDocument]:
        vector = chunk.embedding if chunk.embedding is not None else embed_texts([chunk.text])[0]
        return self._search(vector, exclude_document_id=chunk.document_id)

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[LangChainDocument]:
        return self._search(embed_texts([query])[0], exclude_document_id=self.exclude_document_id)

    def _search(self, vector, exclude_document_id: uuid.UUID | None) -> list[LangChainDocument]:
        # ix_chunks_embedding (ivfflat) was built while the table was empty and searches only
        # one of its lists by default, so it can skip true neighbours. This setting lasts
        # only for the current transaction.
        self.db.execute(text("SET LOCAL enable_indexscan = off"))
        distance = Chunk.embedding.cosine_distance(vector)
        query = (
            select(Chunk, Document, distance.label("distance"))
            .join(Document, Chunk.document_id == Document.id)
            .where(Chunk.embedding.is_not(None))
            .order_by(distance, Chunk.id)
            .limit(self.k)
        )
        if exclude_document_id is not None:
            query = query.where(Chunk.document_id != exclude_document_id)
        return [
            to_langchain_document(chunk, document, 1 - dist)
            for chunk, document, dist in self.db.execute(query)
        ]
