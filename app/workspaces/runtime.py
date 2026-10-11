from functools import lru_cache

from app.agent.agent import RAGAgent
from app.agent.planner import AgentPlanner
from app.agent.router import QueryRouter
from app.agent.tools import RetrievalTool
from app.core.config import get_settings
from app.llm.local_llm import OllamaLLM
from app.rag.generator import RAGGenerator
from app.retrieval.reranker import LexicalReranker
from app.retrieval.retriever import Retriever
from app.vectorstore.index_manager import IndexManager
from app.workspaces.indexing import _build_embedding_model, _build_vector_store
from app.workspaces.store import WorkspaceStore


@lru_cache(maxsize=1)
def _llm() -> OllamaLLM:
    settings = get_settings()
    return OllamaLLM(settings.llm_base_url, settings.llm_model, settings.llm_timeout_seconds)


def build_workspace_agent(workspace_id: str, workspace_store: WorkspaceStore) -> RAGAgent:
    """Build a workspace-isolated agent using its dedicated vector index."""
    settings = get_settings()
    vector_dir = workspace_store.vector_dir(workspace_id)
    index_name = "index.faiss" if settings.vector_store_backend.strip().lower() == "faiss" else "index.npy"
    store = _build_vector_store(settings, vector_dir / index_name, vector_dir / "chunks.json")
    store.load()
    manager = IndexManager(_build_embedding_model(settings), store)
    retriever = Retriever(manager, LexicalReranker(), settings.retrieval_min_score, settings.rerank_min_score)
    return RAGAgent(QueryRouter(), AgentPlanner(), RetrievalTool(retriever, settings.top_k, settings.rerank_top_k), RAGGenerator(_llm()), None)
