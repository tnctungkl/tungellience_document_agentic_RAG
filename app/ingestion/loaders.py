from pathlib import Path

from app.core.exceptions import IngestionError
from app.validation.schemas import Document


class DocumentLoader:
    """Base interface for source document loaders."""

    extensions: frozenset[str] = frozenset()

    def __init__(self, max_size_mb: int = 25) -> None:
        self.max_size_mb = max_size_mb

    def load(self, path: Path) -> Document:
        raise NotImplementedError

    def _validate_file(self, path: Path) -> Path:
        """Validate a file without following symlink input paths."""
        if path.is_symlink():
            raise IngestionError("symlink inputs are not allowed")
        if not path.exists():
            raise IngestionError(f"document does not exist: {path}")
        if not path.is_file():
            raise IngestionError(f"document is not a regular file: {path}")
        size_limit = self.max_size_mb * 1024 * 1024
        if path.stat().st_size > size_limit:
            raise IngestionError("document exceeds configured size limit")
        return path


class TextLoader(DocumentLoader):
    """Loader for plain text and Markdown files."""

    extensions = frozenset({".txt", ".md", ".markdown"})

    def load(self, path: Path) -> Document:
        self._validate_file(path)
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise IngestionError("document is not valid UTF-8") from exc
        return Document(
            source_path=str(path.resolve()),
            file_name=path.name,
            document_type=path.suffix.lower().lstrip("."),
            content=content,
        )


class PdfLoader(DocumentLoader):
    """Loader for text-based PDF documents."""

    extensions = frozenset({".pdf"})

    def load(self, path: Path) -> Document:
        self._validate_file(path)
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise IngestionError("pypdf is required for PDF ingestion") from exc
        try:
            reader = PdfReader(str(path))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as exc:
            raise IngestionError("failed to read PDF document") from exc
        if not text.strip():
            raise IngestionError("PDF contains no extractable text")
        return Document(
            source_path=str(path.resolve()),
            file_name=path.name,
            document_type="pdf",
            content=text,
        )


class DocxLoader(DocumentLoader):
    """Loader for DOCX paragraph content."""

    extensions = frozenset({".docx"})

    def load(self, path: Path) -> Document:
        self._validate_file(path)
        try:
            from docx import Document as DocxDocument
        except ImportError as exc:
            raise IngestionError("python-docx is required for DOCX ingestion") from exc
        try:
            source = DocxDocument(str(path))
            text = "\n".join(p.text for p in source.paragraphs if p.text.strip())
        except Exception as exc:
            raise IngestionError("failed to read DOCX document") from exc
        if not text.strip():
            raise IngestionError("DOCX contains no extractable text")
        return Document(
            source_path=str(path.resolve()),
            file_name=path.name,
            document_type="docx",
            content=text,
        )


class LoaderRegistry:
    """Resolve an appropriate loader from a file suffix."""

    def __init__(self, max_size_mb: int = 25) -> None:
        self.max_size_mb = max_size_mb
        self._loaders = [TextLoader(max_size_mb), PdfLoader(max_size_mb), DocxLoader(max_size_mb)]

    def load(self, path: Path) -> Document:
        suffix = path.suffix.lower()
        for loader in self._loaders:
            if suffix in loader.extensions:
                # Apply the configured size limit consistently across loaders.
                loader._validate_file(path)
                return loader.load(path)
        raise IngestionError(f"unsupported document extension: {suffix or '<none>'}")
