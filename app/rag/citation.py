from app.validation.schemas import Citation, SearchResult


def build_citations(results: list[SearchResult]) -> list[Citation]:
    """Create stable citations from retrieved chunks."""
    return [
        Citation(
            source=result.chunk.metadata.get("source_path", result.chunk.metadata.get("file_name", "unknown")),
            chunk_id=str(result.chunk.id),
            score=float(result.rerank_score if result.rerank_score is not None else result.vector_score),
        )
        for result in results
    ]
