from uuid import UUID

from app.core.exceptions import ProcessingError
from app.validation.schemas import Document, DocumentChunk


def chunk_document(document: Document, chunk_size: int, overlap: int) -> list[DocumentChunk]:
    """Split text using deterministic character windows with bounded overlap."""
    if chunk_size <= 0:
        raise ProcessingError("chunk_size must be positive")
    if overlap < 0 or overlap >= chunk_size:
        raise ProcessingError("overlap must be >= 0 and smaller than chunk_size")

    text = document.content
    if not text.strip():
        return []

    step = chunk_size - overlap
    chunks: list[DocumentChunk] = []
    start = 0
    index = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk_text = text[start:end].strip()
        if chunk_text:
            chunks.append(
                DocumentChunk(
                    document_id=UUID(str(document.id)),
                    chunk_index=index,
                    text=chunk_text,
                    metadata=document.metadata.copy(),
                )
            )
            index += 1
        if end >= len(text):
            break
        start += step

    return chunks
