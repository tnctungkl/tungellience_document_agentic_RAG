from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.exceptions import ProcessingError
from app.processing.chunker import chunk_document
from app.processing.cleaner import clean_text
from app.processing.metadata import build_document_metadata
from app.validation.schemas import Document


def test_cleaner_preserves_paragraph_boundaries():
    value = clean_text('  Hello   world\n\n\nSecond   line  ')
    assert value == 'Hello world\n\nSecond line'


def test_chunker_is_deterministic_for_same_document():
    document = Document(id=uuid4(), source_path='/tmp/a.txt', file_name='a.txt', document_type='txt', content='abcdefghij')
    left = chunk_document(document, 6, 2)
    right = chunk_document(document, 6, 2)
    assert [c.text for c in left] == [c.text for c in right]
    assert [c.chunk_index for c in left] == [0, 1]


def test_chunker_rejects_invalid_overlap():
    document = Document(source_path='a', file_name='a', document_type='txt', content='hello')
    with pytest.raises(ProcessingError):
        chunk_document(document, 10, 10)


def test_metadata_contains_source_information(tmp_path):
    path = tmp_path / 'guide.md'
    document = Document(source_path=str(path), file_name='guide.md', document_type='md', content='hello')
    metadata = build_document_metadata(path, document)
    assert metadata['file_name'] == 'guide.md'
    assert metadata['suffix'] == 'md'
