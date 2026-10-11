import re


def rewrite_query(query: str) -> str:
    """Apply a deterministic query cleanup before vector retrieval."""
    cleaned = re.sub(r"\s+", " ", query.strip())
    cleaned = re.sub(r"[?!.]+$", "", cleaned)
    return cleaned
