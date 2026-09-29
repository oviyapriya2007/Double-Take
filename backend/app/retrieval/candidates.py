"""Automatic candidate-pair generation: which cross-document chunk pairs are worth comparing.

Four retrieval signals are combined:

    semantic_score = W_TFIDF * tfidf_score
                   + W_EMBEDDING * embedding_score
                   + W_ENTITY * entity_overlap
    combined_score = (1 - W_TECHNICAL) * semantic_score
                   + W_TECHNICAL * technical_compatibility

technical_compatibility (app.nlp.technical_claims) rewards two chunks that state comparable
technical claims (quantities with the same unit, time intervals, variant specifications)
about the same subject, which chunk-level similarity misses when those claims sit in long
multi-topic chunks.

1. Every pair of chunks from different documents is scored with combined_score; no signal
   filters pairs out before that.
2. The pairs are ranked by combined_score and MAX_CANDIDATES pairs are kept: first
   each document gets up to MIN_PAIRS_PER_DOCUMENT of its best-scoring pairs, then the rest
   of the budget goes to the highest-scoring remaining pairs, at most
   MAX_PAIRS_PER_DOCUMENT_PAIR from any one pair of documents while other pairs remain.
   This stops a group of near-identical documents from taking the whole budget.

A high score only means two chunks probably describe the same subject. Whether they
contradict each other is decided later by Claude, never here.
"""

import uuid
from collections import Counter
from dataclasses import dataclass
from itertools import combinations

import numpy as np

from app.models import Chunk
from app.nlp.technical_claims import extract_technical_claims, technical_compatibility
from app.nlp.tfidf import tfidf_similarity_matrix

CANDIDATE_METHOD = "combined"
"""candidate_pairs.method for pairs chosen by the combined score."""

W_TFIDF = 0.35
W_EMBEDDING = 0.45
W_ENTITY = 0.20
W_TECHNICAL = 0.20
"""Share of combined_score given to technical_compatibility. The remaining 0.80 keeps the
three weights above in their 0.35 : 0.45 : 0.20 proportions, so the effective weights are
0.28 TF-IDF, 0.36 embedding, 0.16 entity overlap and 0.20 technical compatibility."""

MAX_CANDIDATES = 60
MIN_PAIRS_PER_DOCUMENT = 3
MAX_PAIRS_PER_DOCUMENT_PAIR = 5


@dataclass(frozen=True)
class Candidate:
    chunk_a: Chunk
    chunk_b: Chunk
    tfidf_score: float
    embedding_score: float
    entity_overlap: float
    technical_compatibility: float
    combined_score: float


@dataclass(frozen=True)
class CandidateSelection:
    candidates: list[Candidate]
    """The kept pairs, highest combined_score first."""
    cross_document_pairs: int
    """How many pairs of chunks from different documents exist among the input chunks."""
    scored_pairs: int
    """How many pairs were given a combined_score; equals cross_document_pairs."""


def combined_score(tfidf: float, embedding: float, overlap: float, technical: float) -> float:
    """The weighted retrieval score of one chunk pair; in [0, 1] when every signal is."""
    semantic = W_TFIDF * tfidf + W_EMBEDDING * embedding + W_ENTITY * overlap
    return (1 - W_TECHNICAL) * semantic + W_TECHNICAL * technical


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


def select_with_document_coverage(
    ranked: list[Candidate],
    max_candidates: int,
    min_per_document: int = MIN_PAIRS_PER_DOCUMENT,
    max_per_document_pair: int = MAX_PAIRS_PER_DOCUMENT_PAIR,
) -> list[Candidate]:
    """Keep max_candidates of `ranked` (best first) while letting every document contribute.

    1. Coverage, in rounds 1..min_per_document: in round r, each document that is part of
       fewer than r kept pairs adds its best-scoring pair not yet kept. A pair counts for
       both of its documents. Picks within a round are added best first.
    2. Fill by combined score, keeping at most max_per_document_pair pairs from any one
       pair of documents, so near-identical documents cannot take the whole budget.
    3. If budget is still left, fill by combined score without that limit.

    The result is best first.
    """
    documents_of = [(c.chunk_a.document_id, c.chunk_b.document_id) for c in ranked]
    pairs_by_document: dict[uuid.UUID | None, list[int]] = {}
    for n, pair_documents in enumerate(documents_of):
        for document_id in pair_documents:
            pairs_by_document.setdefault(document_id, []).append(n)

    kept: set[int] = set()
    coverage: Counter = Counter()
    for target in range(1, min_per_document + 1):
        picks = set()
        for document_id, indices in pairs_by_document.items():
            if coverage[document_id] >= target:
                continue
            best = next((n for n in indices if n not in kept), None)
            if best is not None:
                picks.add(best)
        for n in sorted(picks):
            if len(kept) >= max_candidates:
                break
            kept.add(n)
            coverage.update(documents_of[n])

    per_document_pair = Counter(frozenset(documents_of[n]) for n in kept)
    for n in range(len(ranked)):
        if len(kept) >= max_candidates:
            break
        document_pair = frozenset(documents_of[n])
        if n not in kept and per_document_pair[document_pair] < max_per_document_pair:
            kept.add(n)
            per_document_pair[document_pair] += 1

    for n in range(len(ranked)):
        if len(kept) >= max_candidates:
            break
        kept.add(n)

    return [ranked[n] for n in sorted(kept)]


def generate_candidates(
    chunks: list[Chunk],
    entity_types: dict[uuid.UUID, set[str]],
    max_candidates: int = MAX_CANDIDATES,
) -> CandidateSelection:
    """Pick the cross-document chunk pairs worth sending to contradiction analysis.

    Every cross-document pair is scored, so the cost grows with the square of the number
    of chunks. entity_types maps a chunk id to the set of entity types stored for that
    chunk. In each pair, chunk_a is the chunk that comes first in `chunks`, so a fixed
    input order gives the same pairs and order on every run.
    """
    embedding_sim = embedding_similarity_matrix(chunks)
    tfidf_sim = tfidf_similarity_matrix([chunk.text for chunk in chunks])
    claims = [extract_technical_claims(chunk.text) for chunk in chunks]

    chunks_per_document = Counter(chunk.document_id for chunk in chunks)
    cross_document_pairs = (
        len(chunks) ** 2 - sum(n ** 2 for n in chunks_per_document.values())
    ) // 2

    scored = []
    for i, j in combinations(range(len(chunks)), 2):
        if chunks[i].document_id == chunks[j].document_id:
            continue
        tfidf = float(tfidf_sim[i, j])
        embedding = float(embedding_sim[i, j])
        overlap = entity_overlap(
            entity_types.get(chunks[i].id, set()), entity_types.get(chunks[j].id, set())
        )
        technical = technical_compatibility(claims[i], claims[j])
        combined = combined_score(tfidf, embedding, overlap, technical)
        candidate = Candidate(chunks[i], chunks[j], tfidf, embedding, overlap, technical, combined)
        scored.append((combined, i, j, candidate))
    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    ranked = [candidate for *_, candidate in scored]

    return CandidateSelection(
        candidates=select_with_document_coverage(ranked, max_candidates),
        cross_document_pairs=cross_document_pairs,
        scored_pairs=len(scored),
    )
