import numpy as np
import pytest

from app.core.exceptions import VectorStoreError
from app.embeddings.model import HashEmbeddingModel
from app.validation.schemas import DocumentChunk
from app.vectorstore.faiss_store import NumpyVectorStore


def make_chunk(text, index=0):
    from uuid import uuid4
    return DocumentChunk(document_id=uuid4(), chunk_index=index, text=text, metadata={'file_name': 'test.txt'})


def test_numpy_store_upsert_search_and_reload(tmp_path):
    model = HashEmbeddingModel(32)
    store = NumpyVectorStore(32, tmp_path / 'index.npy', tmp_path / 'metadata.json')
    chunks = [make_chunk('python backend service'), make_chunk('annual leave policy')]
    vectors = model.embed([c.text for c in chunks])
    store.upsert(chunks, vectors)
    result = store.search(model.embed(['annual leave'])[0], 2)
    assert result[0].chunk.text == 'annual leave policy'
    store.save()
    loaded = NumpyVectorStore(32, tmp_path / 'index.npy', tmp_path / 'metadata.json')
    loaded.load()
    assert loaded.size == 2


def test_store_rejects_duplicate_ids(tmp_path):
    store = NumpyVectorStore(8, tmp_path / 'i.npy', tmp_path / 'm.json')
    chunk = make_chunk('hello')
    vectors = np.ones((1, 8), dtype=np.float32)
    store.upsert([chunk], vectors)
    with pytest.raises(VectorStoreError):
        store.upsert([chunk], vectors)


def test_store_rejects_bad_query(tmp_path):
    store = NumpyVectorStore(8, tmp_path / 'i.npy', tmp_path / 'm.json')
    with pytest.raises(VectorStoreError):
        store.search(np.zeros(8, dtype=np.float32), 1)
