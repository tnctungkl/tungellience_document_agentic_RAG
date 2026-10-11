from __future__ import annotations

import shutil
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings
from app.core.exceptions import EmbeddingError, IngestionError, VectorStoreError
from app.core.file_transactions import publish_artifacts_atomically
from app.embeddings.model import HashEmbeddingModel, SentenceTransformerEmbeddingModel
from app.ingestion.index_builder import write_chunks_jsonl
from app.ingestion.pipeline import IngestionPipeline
from app.vectorstore.faiss_store import FaissVectorStore, NumpyVectorStore
from app.vectorstore.index_manager import IndexManager


def build_embedding_model(settings):
    """Construct only the embedding provider explicitly selected by configuration."""
    provider = settings.embedding_provider.strip().lower()
    if provider == "hash":
        return HashEmbeddingModel(settings.embedding_dimension)
    if provider == "sentence_transformers":
        return SentenceTransformerEmbeddingModel(settings.embedding_model, settings.embedding_dimension)
    raise EmbeddingError(f"unsupported embedding provider: {settings.embedding_provider}")


def build_vector_store(settings, index_path: Path, metadata_path: Path):
    """Construct the configured vector store at a temporary destination."""
    backend = settings.vector_store_backend.strip().lower()
    if backend == "numpy":
        return NumpyVectorStore(settings.embedding_dimension, index_path, metadata_path)
    if backend == "faiss":
        return FaissVectorStore(settings.embedding_dimension, index_path, metadata_path)
    raise VectorStoreError(f"unsupported vector store backend: {settings.vector_store_backend}")


def main() -> None:
    """Build a fresh global index and publish it only after all work succeeds."""
    settings = get_settings()
    settings.ensure_directories()

    staging_root = settings.raw_data_dir.parent / f".global-index-build-{uuid4().hex}"
    staged_processed = staging_root / "processed" / "chunks.jsonl"
    staged_vector = staging_root / "vector"
    staged_vector.mkdir(parents=True, exist_ok=False)

    try:
        pipeline = IngestionPipeline(settings)
        chunks = pipeline.process_directory(settings.raw_data_dir)
        if not chunks:
            raise IngestionError("no supported documents with extractable text were found")

        write_chunks_jsonl(chunks, staged_processed)
        index_path = staged_vector / ("index.npy" if settings.vector_store_backend.strip().lower() == "numpy" else "index.faiss")
        metadata_path = staged_vector / "chunks.json"
        vector_store = build_vector_store(settings, index_path, metadata_path)
        IndexManager(build_embedding_model(settings), vector_store).add_chunks(chunks)

        destinations = [
            settings.vector_data_dir / "index.faiss",
            settings.vector_data_dir / "index.npy",
            settings.vector_data_dir / "chunks.json",
            settings.processed_data_dir / "chunks.jsonl",
        ]
        replacements = [
            (source, destination)
            for source, destination in (
                (staged_vector / "index.faiss", settings.vector_data_dir / "index.faiss"),
                (staged_vector / "index.npy", settings.vector_data_dir / "index.npy"),
                (staged_vector / "chunks.json", settings.vector_data_dir / "chunks.json"),
                (staged_processed, settings.processed_data_dir / "chunks.jsonl"),
            )
            if source.is_file()
        ]
        publish_artifacts_atomically(
            replacements=replacements,
            managed_destinations=destinations,
            backup_parent=settings.raw_data_dir.parent,
        )
        print(f"Indexed {len(chunks)} chunks using {settings.embedding_provider} + {settings.vector_store_backend}.")
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)


if __name__ == "__main__":
    main()
