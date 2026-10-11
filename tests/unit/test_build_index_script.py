from pathlib import Path

import pytest

from app.core.config import Settings
from app.core.exceptions import EmbeddingError
import scripts.build_index as build_index


def make_settings(tmp_path: Path) -> Settings:
    data = tmp_path / "data"
    raw = data / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "policy.md").write_text(
        "Employees receive 20 days of annual leave. Managers approve requests.",
        encoding="utf-8",
    )
    return Settings(
        embedding_provider="hash",
        vector_store_backend="numpy",
        embedding_dimension=128,
        raw_data_dir=raw,
        processed_data_dir=data / "processed",
        vector_data_dir=data / "vector",
        workspace_data_dir=data / "workspaces",
        workspace_db_path=data / "tungelligence.db",
    )


def test_global_index_build_failure_preserves_existing_artifacts(tmp_path: Path, monkeypatch) -> None:
    settings = make_settings(tmp_path)
    settings.ensure_directories()
    existing_index = settings.vector_data_dir / "index.npy"
    existing_metadata = settings.vector_data_dir / "chunks.json"
    existing_processed = settings.processed_data_dir / "chunks.jsonl"
    existing_index.write_text("old index", encoding="utf-8")
    existing_metadata.write_text("old metadata", encoding="utf-8")
    existing_processed.write_text("old chunks", encoding="utf-8")

    monkeypatch.setattr(build_index, "get_settings", lambda: settings)

    def fail_embedding(_settings):
        raise EmbeddingError("controlled test failure")

    monkeypatch.setattr(build_index, "build_embedding_model", fail_embedding)
    with pytest.raises(EmbeddingError, match="controlled test failure"):
        build_index.main()

    assert existing_index.read_text(encoding="utf-8") == "old index"
    assert existing_metadata.read_text(encoding="utf-8") == "old metadata"
    assert existing_processed.read_text(encoding="utf-8") == "old chunks"
    assert not list(settings.raw_data_dir.parent.glob(".global-index-build-*"))


def test_global_index_build_publishes_complete_numpy_index(tmp_path: Path, monkeypatch) -> None:
    settings = make_settings(tmp_path)
    settings.ensure_directories()
    # A stale artifact from a different backend must not survive a successful rebuild.
    stale_faiss = settings.vector_data_dir / "index.faiss"
    stale_faiss.write_text("stale faiss", encoding="utf-8")
    monkeypatch.setattr(build_index, "get_settings", lambda: settings)

    build_index.main()

    assert (settings.vector_data_dir / "index.npy").is_file()
    assert (settings.vector_data_dir / "chunks.json").is_file()
    assert (settings.processed_data_dir / "chunks.jsonl").is_file()
    assert not stale_faiss.exists()
    assert not list(settings.raw_data_dir.parent.glob(".global-index-build-*"))
