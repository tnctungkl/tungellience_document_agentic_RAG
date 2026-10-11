from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from app.core.config import Settings
from app.core.exceptions import EmbeddingError, IngestionError, VectorStoreError
from app.core.file_transactions import publish_artifacts_atomically
from app.embeddings.model import HashEmbeddingModel, SentenceTransformerEmbeddingModel
from app.ingestion.pipeline import IngestionPipeline
from app.vectorstore.faiss_store import FaissVectorStore, NumpyVectorStore
from app.vectorstore.index_manager import IndexManager
from app.workspaces.store import WorkspaceStore


def _build_embedding_model(settings: Settings):
    """Create the explicitly configured embedding backend."""
    provider = settings.embedding_provider.strip().lower()
    if provider == "hash":
        return HashEmbeddingModel(settings.embedding_dimension)
    if provider == "sentence_transformers":
        return SentenceTransformerEmbeddingModel(settings.embedding_model, settings.embedding_dimension)
    raise EmbeddingError(f"unsupported embedding provider: {settings.embedding_provider}")


def _build_vector_store(settings: Settings, index_path: Path, metadata_path: Path):
    """Create the explicitly configured vector-store backend."""
    backend = settings.vector_store_backend.strip().lower()
    if backend == "numpy":
        return NumpyVectorStore(settings.embedding_dimension, index_path, metadata_path)
    if backend == "faiss":
        return FaissVectorStore(settings.embedding_dimension, index_path, metadata_path)
    raise VectorStoreError(f"unsupported vector store backend: {settings.vector_store_backend}")


def rebuild_workspace_index(workspace_id: str, store: WorkspaceStore, settings: Settings) -> list[dict]:
    """Rebuild one workspace index without destroying its previous working index on failure."""
    raw_dir = store.raw_dir(workspace_id)
    workspace_dir = store._workspace_dir(workspace_id)
    vector_dir = store.vector_dir(workspace_id)
    processed_dir = workspace_dir / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    pipeline = IngestionPipeline(settings)
    chunks = pipeline.process_directory(raw_dir)
    if not chunks:
        raise IngestionError("no supported documents with extractable text were found")

    build_id = uuid4().hex
    build_dir = workspace_dir / f".build-{build_id}"
    build_vector_dir = build_dir / "vector"
    build_processed_dir = build_dir / "processed"
    build_vector_dir.mkdir(parents=True, exist_ok=True)
    build_processed_dir.mkdir(parents=True, exist_ok=True)

    try:
        embedder = _build_embedding_model(settings)
        vector_store = _build_vector_store(
            settings,
            build_vector_dir / "index.faiss" if settings.vector_store_backend.lower() == "faiss" else build_vector_dir / "index.npy",
            build_vector_dir / "chunks.json",
        )
        manager = IndexManager(embedder, vector_store)
        manager.add_chunks(chunks)

        processed_path = build_processed_dir / "chunks.jsonl"
        with processed_path.open("w", encoding="utf-8") as handle:
            for chunk in chunks:
                handle.write(chunk.model_dump_json() + "\n")
            handle.flush()

        documents_by_name: dict[str, dict] = {}
        for chunk in chunks:
            source = chunk.metadata.get("file_name") or chunk.metadata.get("source") or "unknown"
            entry = documents_by_name.setdefault(source, {"file_name": source, "size_bytes": 0, "chunk_count": 0})
            entry["chunk_count"] += 1

        for path in raw_dir.iterdir():
            if path.is_file() and not path.is_symlink():
                try:
                    documents_by_name.setdefault(
                        path.name,
                        {"file_name": path.name, "size_bytes": 0, "chunk_count": 0},
                    )["size_bytes"] = path.stat().st_size
                except OSError:
                    pass

        documents = list(documents_by_name.values())

        # Publish the complete artifact set as one rollback-capable operation.
        vector_targets = [
            vector_dir / "index.faiss",
            vector_dir / "index.npy",
            vector_dir / "chunks.json",
        ]
        processed_target = processed_dir / "chunks.jsonl"
        replacements = [
            (build_vector_dir / filename, vector_dir / filename)
            for filename in ("index.faiss", "index.npy", "chunks.json")
            if (build_vector_dir / filename).is_file()
        ]
        replacements.append((processed_path, processed_target))
        managed_targets = [*vector_targets, processed_target]

        publish_artifacts_atomically(
            replacements=replacements,
            managed_destinations=managed_targets,
            backup_parent=workspace_dir,
            after_publish=lambda: store.replace_documents(workspace_id, documents),
        )
        # Return persisted records so the API response contains generated IDs and timestamps.
        return store.list_documents(workspace_id)
    except (EmbeddingError, VectorStoreError, IngestionError):
        raise
    except OSError as exc:
        raise IngestionError("failed to persist the workspace index") from exc
    finally:
        shutil.rmtree(build_dir, ignore_errors=True)

def clear_workspace_index(workspace_id: str, store: WorkspaceStore) -> None:
    """Remove all derived index artifacts after the workspace has no raw documents."""
    workspace_dir = store._workspace_dir(workspace_id)
    for relative_path in (
        Path("vector/index.faiss"),
        Path("vector/index.npy"),
        Path("vector/chunks.json"),
        Path("processed/chunks.jsonl"),
    ):
        path = workspace_dir / relative_path
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise IngestionError(f"failed to remove index artifact: {relative_path.as_posix()}") from exc

    store.clear_documents(workspace_id)

