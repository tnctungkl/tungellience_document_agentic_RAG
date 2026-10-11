from abc import ABC, abstractmethod
import hashlib

import numpy as np

from app.core.exceptions import EmbeddingError


class EmbeddingModel(ABC):
    """Embedding backend contract used by the vector store."""

    dimension: int

    @abstractmethod
    def embed(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError


def _validate_matrix(matrix: np.ndarray, expected_dimension: int) -> np.ndarray:
    """Validate and normalize embedding matrix layout and values."""
    result = np.asarray(matrix, dtype=np.float32)
    if result.ndim != 2 or result.shape[1] != expected_dimension:
        raise EmbeddingError("embedding matrix has an unexpected shape")
    if not np.isfinite(result).all():
        raise EmbeddingError("embedding matrix contains non-finite values")
    norms = np.linalg.norm(result, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise EmbeddingError("embedding matrix contains zero vectors")
    result = result / norms
    return np.ascontiguousarray(result, dtype=np.float32)


class SentenceTransformerEmbeddingModel(EmbeddingModel):
    """Production embedding backend based on Sentence Transformers."""

    def __init__(self, model_name: str, dimension: int | None = None) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingError("sentence-transformers is required for this backend") from exc
        try:
            self._model = SentenceTransformer(model_name)
            inferred = int(self._model.get_sentence_embedding_dimension())
        except Exception as exc:
            raise EmbeddingError(f"failed to load embedding model: {model_name}") from exc
        self.dimension = dimension or inferred
        if self.dimension != inferred:
            raise EmbeddingError(f"configured dimension {self.dimension} does not match model dimension {inferred}")

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        try:
            vectors = self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True, show_progress_bar=False)
        except Exception as exc:
            raise EmbeddingError("embedding generation failed") from exc
        return _validate_matrix(vectors, self.dimension)


class HashEmbeddingModel(EmbeddingModel):
    """Small deterministic local backend used for tests and offline development."""

    def __init__(self, dimension: int = 128) -> None:
        self.dimension = dimension

    def embed(self, texts: list[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for row, text in enumerate(texts):
            tokens = [token for token in text.lower().split() if token]
            for token in tokens:
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                index = int.from_bytes(digest, "big") % self.dimension
                vectors[row, index] += 1.0
            if not tokens:
                vectors[row, 0] = 1.0
        return _validate_matrix(vectors, self.dimension)
