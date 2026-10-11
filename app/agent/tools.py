from app.retrieval.retriever import Retriever


class RetrievalTool:
    """Tool wrapper exposed to the agent controller."""

    def __init__(self, retriever: Retriever, top_k: int, rerank_top_k: int) -> None:
        self.retriever = retriever
        self.top_k = top_k
        self.rerank_top_k = rerank_top_k

    def run(self, query: str):
        return self.retriever.retrieve(query, self.top_k, self.rerank_top_k)
