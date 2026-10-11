import numpy as np
import pytest

from app.core.exceptions import EmbeddingError
from app.embeddings.model import HashEmbeddingModel, _validate_matrix


def test_hash_embeddings_are_normalized_and_deterministic():
    model = HashEmbeddingModel(32)
    first = model.embed(['hello world'])
    second = model.embed(['hello world'])
    assert first.shape == (1, 32)
    assert np.allclose(first, second)
    assert np.isclose(np.linalg.norm(first[0]), 1.0)


def test_empty_embeddings_have_correct_shape():
    model = HashEmbeddingModel(16)
    assert model.embed([]).shape == (0, 16)


def test_invalid_embedding_matrix_is_rejected():
    with pytest.raises(EmbeddingError):
        _validate_matrix(np.ones((2, 8)), 4)


def test_zero_vector_is_rejected():
    with pytest.raises(EmbeddingError):
        _validate_matrix(np.zeros((1, 4)), 4)
