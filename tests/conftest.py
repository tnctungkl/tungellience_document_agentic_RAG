import pytest

from app.embeddings.model import HashEmbeddingModel
from app.vectorstore.faiss_store import NumpyVectorStore
from app.vectorstore.index_manager import IndexManager


@pytest.fixture()
def vector_runtime(tmp_path):
    embedder = HashEmbeddingModel(64)
    store = NumpyVectorStore(64, tmp_path / 'vectors.npy', tmp_path / 'chunks.json')
    return embedder, store, IndexManager(embedder, store)
