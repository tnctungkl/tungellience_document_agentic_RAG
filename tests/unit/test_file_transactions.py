from pathlib import Path

import pytest

from app.core.file_transactions import publish_artifacts_atomically


def test_artifact_publish_restores_previous_files_when_callback_fails(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    staged_index = stage / "index.npy"
    staged_index.write_text("new index", encoding="utf-8")
    staged_metadata = stage / "chunks.json"
    staged_metadata.write_text("new metadata", encoding="utf-8")

    target_dir = tmp_path / "vector"
    target_dir.mkdir()
    index_path = target_dir / "index.npy"
    index_path.write_text("old index", encoding="utf-8")
    stale_faiss_path = target_dir / "index.faiss"
    stale_faiss_path.write_text("old faiss", encoding="utf-8")
    metadata_path = target_dir / "chunks.json"
    metadata_path.write_text("old metadata", encoding="utf-8")

    def fail_after_publish() -> None:
        raise RuntimeError("database update failed")

    with pytest.raises(RuntimeError, match="database update failed"):
        publish_artifacts_atomically(
            replacements=[(staged_index, index_path), (staged_metadata, metadata_path)],
            managed_destinations=[index_path, stale_faiss_path, metadata_path],
            backup_parent=tmp_path,
            after_publish=fail_after_publish,
        )

    assert index_path.read_text(encoding="utf-8") == "old index"
    assert stale_faiss_path.read_text(encoding="utf-8") == "old faiss"
    assert metadata_path.read_text(encoding="utf-8") == "old metadata"
    assert not list(tmp_path.glob(".artifact-backup-*"))


def test_artifact_publish_removes_stale_backend_artifact_on_success(tmp_path: Path) -> None:
    stage = tmp_path / "stage"
    stage.mkdir()
    staged_index = stage / "index.npy"
    staged_index.write_text("new numpy index", encoding="utf-8")

    vector_dir = tmp_path / "vector"
    vector_dir.mkdir()
    index_path = vector_dir / "index.npy"
    index_path.write_text("old numpy index", encoding="utf-8")
    stale_faiss_path = vector_dir / "index.faiss"
    stale_faiss_path.write_text("old faiss index", encoding="utf-8")

    publish_artifacts_atomically(
        replacements=[(staged_index, index_path)],
        managed_destinations=[index_path, stale_faiss_path],
        backup_parent=tmp_path,
    )

    assert index_path.read_text(encoding="utf-8") == "new numpy index"
    assert not stale_faiss_path.exists()
