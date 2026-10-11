from pathlib import Path

from app.validation.schemas import Document


def build_document_metadata(path: Path, document: Document) -> dict[str, str]:
    """Build stable metadata needed by retrieval, citations, and UI."""
    return {
        **document.metadata,
        "source_path": document.source_path,
        "file_name": document.file_name,
        "document_type": document.document_type,
        "suffix": path.suffix.lower().lstrip("."),
    }
