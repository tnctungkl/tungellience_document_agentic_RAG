from pathlib import Path

import pytest

from app.core.exceptions import IngestionError
from app.core.config import Settings
from app.ingestion.index_builder import build_processed_dataset
from app.ingestion.loaders import DocxLoader, LoaderRegistry, PdfLoader, TextLoader
from app.ingestion.pipeline import IngestionPipeline


def test_text_loader_and_registry(tmp_path):
    path = tmp_path / 'a.txt'
    path.write_text('Hello\n\nWorld', encoding='utf-8')
    document = TextLoader().load(path)
    assert document.file_name == 'a.txt'
    assert 'Hello' in document.content
    assert LoaderRegistry().load(path).document_type == 'txt'


def test_registry_rejects_unsupported(tmp_path):
    path = tmp_path / 'a.bin'
    path.write_bytes(b'abc')
    with pytest.raises(IngestionError, match='unsupported'):
        LoaderRegistry().load(path)


def test_loader_rejects_missing_and_symlink(tmp_path):
    with pytest.raises(IngestionError, match='does not exist'):
        TextLoader().load(tmp_path / 'missing.txt')
    source = tmp_path / 'source.txt'
    source.write_text('safe', encoding='utf-8')
    link = tmp_path / 'link.txt'
    link.symlink_to(source)
    with pytest.raises(IngestionError, match='symlink'):
        TextLoader().load(link)


def test_pipeline_and_jsonl(tmp_path):
    raw = tmp_path / 'raw'; raw.mkdir()
    processed = tmp_path / 'processed'
    file = raw / 'guide.md'
    file.write_text('Title\n\nUseful policy information.', encoding='utf-8')
    settings = Settings(raw_data_dir=raw, processed_data_dir=processed, vector_data_dir=tmp_path/'vector', chunk_size=100, chunk_overlap=10)
    pipeline = IngestionPipeline(settings)
    chunks = pipeline.process_file(file)
    assert chunks and chunks[0].metadata['file_name'] == 'guide.md'
    output = processed / 'chunks.jsonl'
    assert build_processed_dataset(pipeline, raw, output) == len(chunks)
    assert output.read_text(encoding='utf-8').strip()


def test_pipeline_rejects_non_directory(tmp_path):
    settings = Settings(raw_data_dir=tmp_path, processed_data_dir=tmp_path/'p', vector_data_dir=tmp_path/'v')
    file = tmp_path/'file.txt'; file.write_text('x', encoding='utf-8')
    with pytest.raises(IngestionError):
        IngestionPipeline(settings).process_directory(file)


def test_docx_loader(tmp_path):
    from docx import Document as WordDocument
    path = tmp_path / 'guide.docx'
    doc = WordDocument(); doc.add_paragraph('Policy details'); doc.save(path)
    result = DocxLoader().load(path)
    assert result.document_type == 'docx'


def test_invalid_utf8(tmp_path):
    path = tmp_path / 'bad.txt'
    path.write_bytes(bytes([0xFF, 0xFE]))
    with pytest.raises(IngestionError, match='UTF-8'):
        TextLoader().load(path)


def test_loader_honors_configured_size_limit(tmp_path):
    path = tmp_path / 'large.txt'
    path.write_text('abcdefghij', encoding='utf-8')
    # Use a zero-sized configuration boundary without creating a huge fixture.
    with pytest.raises(IngestionError, match='size limit'):
        TextLoader(max_size_mb=0).load(path)


def test_pipeline_rejects_symlink(tmp_path):
    target = tmp_path / 'safe.txt'
    target.write_text('safe', encoding='utf-8')
    link = tmp_path / 'link.txt'
    link.symlink_to(target)
    settings = Settings(raw_data_dir=tmp_path, processed_data_dir=tmp_path/'p', vector_data_dir=tmp_path/'v')
    with pytest.raises(IngestionError, match='symlink'):
        IngestionPipeline(settings).process_file(link)
