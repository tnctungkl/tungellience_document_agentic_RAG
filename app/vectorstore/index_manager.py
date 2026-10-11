from pathlib import Path

import numpy as np

from app.core.exceptions import VectorStoreError
from app.embeddings.model import EmbeddingModel
from app.validation.schemas import DocumentChunk, SearchResult
from app.vectorstore.faiss_store import VectorStore


class IndexManager:
    """Coordinate embedding generation and vector-store persistence."""

    def __init__(self, embedder: EmbeddingModel, store: VectorStore) -> None:
        self.embedder = embedder
        self.store = store

    def add_chunks(self, chunks: list[DocumentChunk]) -> None:
        if not chunks:
            return
        vectors = self.embedder.embed([chunk.text for chunk in chunks])
        if vectors.shape[0] != len(chunks):
            raise VectorStoreError("embedding count mismatch")
        self.store.upsert(chunks, vectors)
        self.store.save()

    def search(self, query: str, top_k: int) -> list[SearchResult]:
        if not query.strip():
            raise VectorStoreError("query must contain text")
        vector = self.embedder.embed([query])
        return self.store.search(vector[0], top_k)
