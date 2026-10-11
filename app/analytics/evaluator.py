from app.analytics.metrics import RetrievalMetrics, compute_retrieval_metrics
from app.retrieval.retriever import Retriever


class RAGEvaluator:
    """Evaluate retrieval behavior against a small labeled dataset."""

    def __init__(self, retriever: Retriever, top_k: int = 5, rerank_top_k: int = 3) -> None:
        self.retriever = retriever
        self.top_k = top_k
        self.rerank_top_k = rerank_top_k

    def evaluate(self, dataset: list[dict[str, str]]) -> RetrievalMetrics:
        rows = []
        for item in dataset:
            _, results, _ = self.retriever.retrieve(item["query"], self.top_k, self.rerank_top_k)
            rows.append(([str(result.chunk.id) for result in results], item["expected_chunk_id"]))
        return compute_retrieval_metrics(rows)
