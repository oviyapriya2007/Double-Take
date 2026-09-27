import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

EMBEDDING_DIM = 384


def uuid_pk_column() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


def timestamp_column() -> Mapped[datetime | None]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = uuid_pk_column()
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text)
    doc_type: Mapped[str | None] = mapped_column(Text)
    uploaded_at: Mapped[datetime | None] = timestamp_column()

    chunks: Mapped[list["Chunk"]] = relationship(
        back_populates="document", passive_deletes=True
    )


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        Index(
            "ix_chunks_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk_column()
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE")
    )
    section: Mapped[str | None] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    tfidf_vector: Mapped[dict | None] = mapped_column(JSONB)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    created_at: Mapped[datetime | None] = timestamp_column()

    document: Mapped[Document | None] = relationship(back_populates="chunks")
    entities: Mapped[list["Entity"]] = relationship(
        back_populates="chunk", passive_deletes=True
    )


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = uuid_pk_column()
    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chunks.id", ondelete="CASCADE")
    )
    entity_text: Mapped[str | None] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(Text)
    start_char: Mapped[int | None] = mapped_column(Integer)
    end_char: Mapped[int | None] = mapped_column(Integer)

    chunk: Mapped[Chunk | None] = relationship(back_populates="entities")


class CandidatePair(Base):
    __tablename__ = "candidate_pairs"

    id: Mapped[uuid.UUID] = uuid_pk_column()
    chunk_a_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chunks.id"))
    chunk_b_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("chunks.id"))
    tfidf_score: Mapped[float | None] = mapped_column(Float)
    embedding_score: Mapped[float | None] = mapped_column(Float)
    entity_overlap_score: Mapped[float | None] = mapped_column(Float)
    combined_score: Mapped[float | None] = mapped_column(Float)
    method: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime | None] = timestamp_column()

    chunk_a: Mapped[Chunk | None] = relationship(foreign_keys=[chunk_a_id])
    chunk_b: Mapped[Chunk | None] = relationship(foreign_keys=[chunk_b_id])
    results: Mapped[list["ContradictionResult"]] = relationship(
        back_populates="candidate_pair"
    )


class ContradictionResult(Base):
    __tablename__ = "contradiction_results"
    __table_args__ = (
        CheckConstraint(
            "verdict IN ('CONTRADICTION','CONSISTENT','UNCERTAIN')",
            name="ck_contradiction_results_verdict",
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk_column()
    candidate_pair_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("candidate_pairs.id")
    )
    verdict: Mapped[str | None] = mapped_column(Text)
    topic: Mapped[str | None] = mapped_column(Text)
    reasoning: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict | list | None] = mapped_column(JSONB)
    confidence: Mapped[float | None] = mapped_column(Float)
    llm_raw_response: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime | None] = timestamp_column()

    candidate_pair: Mapped[CandidatePair | None] = relationship(back_populates="results")
