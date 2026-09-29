"""TF-IDF cosine similarity between chunks of different documents.

TF-IDF weights depend on the corpus, so the vectorizer is fitted on the chunks of the
current analysis each time rather than stored as a fixed model. A high score only means
two chunks use similar wording; it is a retrieval signal, never a contradiction verdict.
"""

from dataclasses import dataclass

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.models import Chunk


@dataclass(frozen=True)
class ChunkPair:
    chunk_a: Chunk
    chunk_b: Chunk
    score: float


def tfidf_similarity_matrix(texts: list[str]) -> np.ndarray:
    """Cosine similarity between the TF-IDF vectors of every pair of texts.

    English stop words are ignored, and sublinear_tf (1 + log of the count) stops a chunk
    from looking similar just because it repeats one word, such as the product name.
    """
    vectorizer = TfidfVectorizer(stop_words="english", sublinear_tf=True)
    return cosine_similarity(vectorizer.fit_transform(texts))


def cross_document_pairs(chunks: list[Chunk], similarity: np.ndarray) -> list[ChunkPair]:
    """Each pair of chunks from different documents with its score, strongest first.

    similarity[i, j] must be the score between chunks[i] and chunks[j]. Every pair is
    listed once, and pairs of chunks from the same document are left out.
    """
    pairs = [
        ChunkPair(chunks[i], chunks[j], float(similarity[i, j]))
        for i in range(len(chunks))
        for j in range(i + 1, len(chunks))
        if chunks[i].document_id != chunks[j].document_id
    ]
    return sorted(pairs, key=lambda pair: pair.score, reverse=True)


def tfidf_cross_document_pairs(chunks: list[Chunk]) -> list[ChunkPair]:
    """Fit TF-IDF on these chunks and return their cross-document pairs, strongest first."""
    return cross_document_pairs(chunks, tfidf_similarity_matrix([chunk.text for chunk in chunks]))
