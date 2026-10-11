from abc import ABC, abstractmethod
from pathlib import Path
from uuid import UUID
import json

import numpy as np

from app.core.exceptions import VectorStoreError
from app.validation.schemas import DocumentChunk, SearchResult


class VectorStore(ABC):
    """Storage contract for vector retrieval backends."""

    @abstractmethod
    def upsert(self, chunks: list[DocumentChunk], vectors: np.ndarray) -> None:
        raise NotImplementedError

    @abstractmethod
    def search(self, vector: np.ndarray, top_k: int) -> list[SearchResult]:
        raise NotImplementedError

    @abstractmethod
    def save(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def load(self) -> None:
        raise NotImplementedError


class NumpyVectorStore(VectorStore):
    """Dependency-light vector store used in tests and offline development."""

    def __init__(self, dimension: int, index_path: Path, metadata_path: Path) -> None:
        self.dimension = dimension
        self.index_path = index_path
        self.metadata_path = metadata_path
        self._vectors = np.empty((0, dimension), dtype=np.float32)
        self._chunks: list[DocumentChunk] = []

    def upsert(self, chunks: list[DocumentChunk], vectors: np.ndarray) -> None:
        vectors = np.asarray(vectors, dtype=np.float32)
        if len(chunks) != len(vectors):
            raise VectorStoreError("chunk/vector count mismatch")
        if vectors.ndim != 2 or vectors.shape[1] != self.dimension:
            raise VectorStoreError("vector dimension mismatch")
        if not np.isfinite(vectors).all():
            raise VectorStoreError("vectors contain non-finite values")
        ids = {str(chunk.id) for chunk in self._chunks}
        if any(str(chunk.id) in ids for chunk in chunks):
            raise VectorStoreError("duplicate chunk id")
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        if len(vectors) and np.any(norms == 0):
            raise VectorStoreError("zero vectors are not allowed")
        normalized = vectors / norms if len(vectors) else vectors
        self._vectors = np.vstack([self._vectors, normalized])
        self._chunks.extend(chunks)

    def search(self, vector: np.ndarray, top_k: int) -> list[SearchResult]:
        if top_k <= 0:
            raise VectorStoreError("top_k must be positive")
        vector = np.asarray(vector, dtype=np.float32).reshape(-1)
        if vector.shape[0] != self.dimension:
            raise VectorStoreError("query vector dimension mismatch")
        norm = np.linalg.norm(vector)
        if not self._chunks:
            if norm == 0 or not np.isfinite(norm):
                raise VectorStoreError("query vector is invalid")
            return []
        if norm == 0 or not np.isfinite(norm):
            raise VectorStoreError("query vector is invalid")
        query = vector / norm
        scores = self._vectors @ query
        indices = np.argsort(-scores)[: min(top_k, len(self._chunks))]
        return [SearchResult(chunk=self._chunks[i], vector_score=float(scores[i])) for i in indices]

    def clear(self) -> None:
        """Reset the native FAISS index and associated metadata."""
        self.index = self._faiss.IndexFlatIP(self.dimension)
        self._chunks.clear()

    def save(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_index = self.index_path.with_suffix(self.index_path.suffix + ".tmp")
        tmp_meta = self.metadata_path.with_suffix(self.metadata_path.suffix + ".tmp")
        try:
            with tmp_index.open("wb") as handle:
                np.save(handle, self._vectors, allow_pickle=False)
                handle.flush()
            with tmp_meta.open("w", encoding="utf-8") as handle:
                json.dump([chunk.model_dump(mode="json") for chunk in self._chunks], handle, ensure_ascii=False, indent=2)
                handle.flush()
            tmp_index.replace(self.index_path)
            tmp_meta.replace(self.metadata_path)
        except (OSError, TypeError, ValueError) as exc:
            raise VectorStoreError("failed to persist vector store") from exc

    def load(self) -> None:
        if not self.index_path.exists() or not self.metadata_path.exists():
            return
        try:
            with self.index_path.open("rb") as handle:
                vectors = np.load(handle, allow_pickle=False)
            payload = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            chunks = [DocumentChunk.model_validate(item) for item in payload]
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise VectorStoreError("failed to load persisted vector store") from exc
        if vectors.ndim != 2 or vectors.shape[1] != self.dimension or vectors.shape[0] != len(chunks):
            raise VectorStoreError("persisted vector store is inconsistent")
        self._vectors = np.asarray(vectors, dtype=np.float32)
        self._chunks = chunks

    def clear(self) -> None:
        """Remove all indexed vectors and chunk metadata."""
        self._vectors = np.empty((0, self.dimension), dtype=np.float32)
        self._chunks.clear()

    @property
    def size(self) -> int:
        return len(self._chunks)


class FaissVectorStore(VectorStore):
    """FAISS-backed persistent vector store for production-oriented retrieval."""

    def __init__(self, dimension: int, index_path: Path, metadata_path: Path) -> None:
        try:
            import faiss
        except ImportError as exc:
            raise VectorStoreError("faiss-cpu is required for the FAISS backend") from exc
        self._faiss = faiss
        self.dimension = dimension
        self.index_path = index_path
        self.metadata_path = metadata_path
        self.index = faiss.IndexFlatIP(dimension)
        self._chunks: list[DocumentChunk] = []

    def upsert(self, chunks: list[DocumentChunk], vectors: np.ndarray) -> None:
        if len(chunks) != len(vectors):
            raise VectorStoreError("chunk/vector count mismatch")
        vectors = np.asarray(vectors, dtype=np.float32)
        if vectors.ndim != 2 or vectors.shape[1] != self.dimension or not np.isfinite(vectors).all():
            raise VectorStoreError("invalid FAISS vector matrix")
        if len(vectors):
            self._faiss.normalize_L2(vectors)
            self.index.add(np.ascontiguousarray(vectors))
            self._chunks.extend(chunks)

    def search(self, vector: np.ndarray, top_k: int) -> list[SearchResult]:
        if top_k <= 0:
            raise VectorStoreError("top_k must be positive")
        if self.index.ntotal == 0:
            return []
        vector = np.asarray(vector, dtype=np.float32).reshape(1, -1)
        if vector.shape[1] != self.dimension or not np.isfinite(vector).all():
            raise VectorStoreError("invalid query vector")
        self._faiss.normalize_L2(vector)
        scores, indices = self.index.search(vector, min(top_k, self.index.ntotal))
        results = []
        for score, index in zip(scores[0], indices[0]):
            if index < 0:
                continue
            results.append(SearchResult(chunk=self._chunks[int(index)], vector_score=float(score)))
        return results

    def save(self) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_index = self.index_path.with_suffix(self.index_path.suffix + ".tmp")
        tmp_meta = self.metadata_path.with_suffix(self.metadata_path.suffix + ".tmp")
        try:
            self._faiss.write_index(self.index, str(tmp_index))
            tmp_meta.write_text(json.dumps([c.model_dump(mode="json") for c in self._chunks], ensure_ascii=False, indent=2), encoding="utf-8")
            tmp_index.replace(self.index_path)
            tmp_meta.replace(self.metadata_path)
        except OSError as exc:
            raise VectorStoreError("failed to persist FAISS store") from exc

    def load(self) -> None:
        if not self.index_path.exists() or not self.metadata_path.exists():
            return
        try:
            self.index = self._faiss.read_index(str(self.index_path))
            payload = json.loads(self.metadata_path.read_text(encoding="utf-8"))
            self._chunks = [DocumentChunk.model_validate(item) for item in payload]
        except Exception as exc:
            raise VectorStoreError("failed to load FAISS store") from exc
        if self.index.d != self.dimension or self.index.ntotal != len(self._chunks):
            raise VectorStoreError("persisted FAISS store is inconsistent")
