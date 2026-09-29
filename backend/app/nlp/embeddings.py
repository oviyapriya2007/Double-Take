"""Sentence embeddings with sentence-transformers/all-MiniLM-L6-v2.

Each chunk becomes one 384-dimensional vector, stored in chunks.embedding (VECTOR(384)).
Chunks whose vectors point in a similar direction have similar meaning even when their
wording differs. This is a retrieval signal only, never a contradiction verdict.
"""

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.models import EMBEDDING_DIM

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def load_model() -> SentenceTransformer:
    """Load the model once per process; the first call downloads it (~90 MB) and caches it."""
    return SentenceTransformer(MODEL_NAME)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """One 384-dimensional embedding per text, scaled to length 1.

    With unit-length vectors, cosine similarity is simply the dot product, and pgvector's
    cosine distance (<=>) gives the same ranking.
    """
    if not texts:
        return []
    vectors = load_model().encode(texts, normalize_embeddings=True, convert_to_numpy=True)
    if vectors.shape[1] != EMBEDDING_DIM:
        raise ValueError(
            f"{MODEL_NAME} returned {vectors.shape[1]}-dimensional vectors, "
            f"but chunks.embedding is VECTOR({EMBEDDING_DIM})"
        )
    return vectors.tolist()
