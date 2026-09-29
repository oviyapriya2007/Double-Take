"""Automatic candidate-pair generation: which cross-document chunk pairs are worth comparing.

Three retrieval signals are combined:

    combined_score = W_TFIDF * tfidf_score
                   + W_EMBEDDING * embedding_score
                   + W_ENTITY * entity_overlap

1. Each chunk's TOP_K_PER_CHUNK most similar chunks from other documents are shortlisted by
   embedding cosine similarity.
2. The shortlist is re-ranked by combined_score and the best MAX_CANDIDATES pairs are kept.

A high score only means two chunks probably describe the same subject. Whether they
contradict each other is decided later by Claude, never here.
"""

import uuid
from dataclasses import dataclass

import numpy as np

from app.models import Chunk
from app.nlp.tfidf import tfidf_similarity_matrix

CANDIDATE_METHOD = "combined"
"""candidate_pairs.method for pairs chosen by the combined score."""

W_TFIDF = 0.35
W_EMBEDDING = 0.45
W_ENTITY = 0.20

TOP_K_PER_CHUNK = 5
MAX_CANDIDATES = 60


@dataclass(frozen=True)
class Candidate:
    chunk_a: Chunk
    chunk_b: Chunk
    tfidf_score: float
    embedding_score: float
    entity_overlap: float
    combined_score: float


@dataclass(frozen=True)
class CandidateSelection:
    candidates: list[Candidate]
    """The kept pairs, highest combined_score first."""
    cross_document_pairs: int
    """How many pairs of chunks from different documents were scored by embedding similarity."""
    shortlisted_pairs: int
    """How many distinct pairs came out of the top-K embedding shortlist."""


def entity_overlap(types_a: set[str], types_b: set[str]) -> float:
    """Jaccard similarity of two chunks' entity types: shared types / all types."""
    all_types = types_a | types_b
    return len(types_a & types_b) / len(all_types) if all_types else 0.0


def embedding_similarity_matrix(chunks: list[Chunk]) -> np.ndarray:
    """Exact cosine similarity between the stored embeddings of every pair of chunks.

    Computed directly from chunks.embedding rather than through the approximate ivfflat
    index, so no candidate can be skipped by the index.
    """
    missing = [str(chunk.id) for chunk in chunks if chunk.embedding is None]
    if missing:
        raise ValueError(f"{len(missing)} chunks have no embedding (e.g. {missing[0]}); "
                         "run embed_and_store_chunks on them first")
    vectors = np.array([np.asarray(chunk.embedding, dtype=np.float64) for chunk in chunks])
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    return vectors @ vectors.T


def generate_candidates(
    chunks: list[Chunk],
    entity_types: dict[uuid.UUID, set[str]],
    top_k: int = TOP_K_PER_CHUNK,
    max_candidates: int = MAX_CANDIDATES,
) -> CandidateSelection:
    """Pick the cross-document chunk pairs worth sending to contradiction analysis.

    entity_types maps a chunk id to the set of entity types stored for that chunk. In each
    pair, chunk_a is the chunk that comes first in `chunks`, so a fixed input order gives
    the same pairs and order on every run.
    """
    embedding_sim = embedding_similarity_matrix(chunks)
    tfidf_sim = tfidf_similarity_matrix([chunk.text for chunk in chunks])

    cross_document_pairs = 0
    shortlist: set[tuple[int, int]] = set()
    for i, chunk in enumerate(chunks):
        others = [j for j, other in enumerate(chunks) if other.document_id != chunk.document_id]
        cross_document_pairs += sum(j > i for j in others)
        nearest = sorted(others, key=lambda j: (-embedding_sim[i, j], j))[:top_k]
        shortlist.update((min(i, j), max(i, j)) for j in nearest)

    scored = []
    for i, j in shortlist:
        tfidf = float(tfidf_sim[i, j])
        embedding = float(embedding_sim[i, j])
        overlap = entity_overlap(
            entity_types.get(chunks[i].id, set()), entity_types.get(chunks[j].id, set())
        )
        combined = W_TFIDF * tfidf + W_EMBEDDING * embedding + W_ENTITY * overlap
        candidate = Candidate(chunks[i], chunks[j], tfidf, embedding, overlap, combined)
        scored.append((combined, i, j, candidate))
    scored.sort(key=lambda item: (-item[0], item[1], item[2]))

    return CandidateSelection(
        candidates=[candidate for *_, candidate in scored[:max_candidates]],
        cross_document_pairs=cross_document_pairs,
        shortlisted_pairs=len(shortlist),
    )
