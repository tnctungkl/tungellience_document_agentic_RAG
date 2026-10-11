from app.core.exceptions import RetrievalError
from app.retrieval.query_expander import rewrite_query
from app.retrieval.reranker import LexicalReranker
from app.validation.schemas import SearchResult
from app.vectorstore.index_manager import IndexManager


class Retriever:
    """Adaptive retrieval service combining vector search and reranking."""

    def __init__(self, index_manager: IndexManager, reranker: LexicalReranker, min_vector_score: float, min_rerank_score: float) -> None:
        self.index_manager = index_manager
        self.reranker = reranker
        self.min_vector_score = min_vector_score
        self.min_rerank_score = min_rerank_score

    def retrieve(self, query: str, top_k: int, rerank_top_k: int) -> tuple[str, list[SearchResult], float]:
        rewritten = rewrite_query(query)
        if not rewritten:
            raise RetrievalError("query is empty after normalization")

        candidates = self.index_manager.search(rewritten, top_k)
        candidates = [item for item in candidates if item.vector_score >= self.min_vector_score]
        if not candidates:
            return rewritten, [], 0.0

        reranked = self.reranker.rerank(rewritten, candidates, rerank_top_k)
        reranked = [item for item in reranked if (item.rerank_score or 0.0) >= self.min_rerank_score]
        if not reranked:
            return rewritten, [], 0.0

        best = max(item.rerank_score or 0.0 for item in reranked)
        confidence = max(0.0, min(1.0, best))
        return rewritten, reranked, confidence
