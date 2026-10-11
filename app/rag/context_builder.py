from app.validation.schemas import SearchResult


def build_context(results: list[SearchResult]) -> tuple[list[str], list[str]]:
    """Prepare context strings and source identifiers for downstream generation."""
    contexts = [result.chunk.text for result in results]
    sources = [result.chunk.metadata.get("file_name", "unknown") for result in results]
    return contexts, sources
