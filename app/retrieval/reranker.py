import math
import re

from app.validation.schemas import SearchResult

_TOKEN_RE = re.compile(r"\b\w+\b", re.UNICODE)


def _token_set(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN_RE.findall(text)}


class LexicalReranker:
    """Lightweight reranker that requires no model download."""

    def score(self, query: str, text: str) -> float:
        query_tokens = _token_set(query)
        text_tokens = _token_set(text)
        if not query_tokens or not text_tokens:
            return 0.0
        overlap = len(query_tokens & text_tokens) / len(query_tokens)
        length_penalty = 1.0 / (1.0 + math.log1p(max(len(text_tokens) - len(query_tokens), 0)) / 10)
        return max(0.0, min(1.0, overlap * length_penalty))

    def rerank(self, query: str, results: list[SearchResult], top_k: int) -> list[SearchResult]:
        scored = [
            result.model_copy(update={"rerank_score": self.score(query, result.chunk.text)})
            for result in results
        ]
        return sorted(scored, key=lambda item: (item.rerank_score or 0.0, item.vector_score), reverse=True)[:top_k]
