from pathlib import Path

from app.core.config import Settings
from app.core.exceptions import IngestionError
from app.ingestion.loaders import LoaderRegistry
from app.processing.chunker import chunk_document
from app.processing.cleaner import clean_text
from app.processing.metadata import build_document_metadata
from app.validation.schemas import DocumentChunk


class IngestionPipeline:
    """Turn supported source files into validated retrieval chunks."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.loader_registry = LoaderRegistry(settings.max_document_size_mb)

    def process_file(self, path: Path) -> list[DocumentChunk]:
        # Validate the path before resolving it so symlinks cannot escape the input boundary.
        if path.is_symlink():
            raise IngestionError("symlink inputs are not allowed")
        if not path.exists() or not path.is_file():
            raise IngestionError(f"document is not a regular file: {path}")
        path = path.resolve()
        document = self.loader_registry.load(path)
        cleaned = clean_text(document.content)
        if not cleaned:
            raise IngestionError(f"document contains no usable text: {path.name}")
        document = document.model_copy(update={"content": cleaned})
        document = document.model_copy(
            update={"metadata": build_document_metadata(path, document)}
        )
        return chunk_document(document, self.settings.chunk_size, self.settings.chunk_overlap)

    def process_directory(self, directory: Path) -> list[DocumentChunk]:
        """Process supported regular files in one directory without recursion."""
        if directory.is_symlink() or not directory.is_dir():
            raise IngestionError("input directory must be a real directory")
        chunks: list[DocumentChunk] = []
        for path in sorted(directory.iterdir()):
            if path.is_file() and not path.is_symlink() and path.suffix.lower() in {".txt", ".md", ".markdown", ".pdf", ".docx"}:
                chunks.extend(self.process_file(path))
        return chunks
