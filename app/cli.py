import argparse

from app.agent.agent import RAGAgent
from app.agent.planner import AgentPlanner
from app.agent.router import QueryRouter
from app.agent.tools import RetrievalTool
from app.core.config import get_settings
from app.embeddings.model import SentenceTransformerEmbeddingModel
from app.llm.base import StaticLLM
from app.llm.local_llm import OllamaLLM
from app.rag.generator import RAGGenerator
from app.retrieval.reranker import LexicalReranker
from app.retrieval.retriever import Retriever
from app.vectorstore.faiss_store import FaissVectorStore
from app.vectorstore.index_manager import IndexManager


from app.api.runtime import build_runtime_agent as build_agent


def main() -> None:
    parser = argparse.ArgumentParser(description="Tungelligence Agentic RAG CLI")
    parser.add_argument("query", help="Question to ask the agent")
    args = parser.parse_args()
    response = build_agent().run(args.query)
    print(response.answer)
    for citation in response.citations:
        print(f"[{citation.score:.3f}] {citation.source}")


if __name__ == "__main__":
    main()
