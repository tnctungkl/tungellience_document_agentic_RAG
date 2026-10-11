from app.agent.document_analysis import DocumentAnalysisTool
from app.agent.agent import RAGAgent
from app.agent.planner import AgentPlanner
from app.agent.router import QueryRouter
from app.agent.tools import RetrievalTool
from app.embeddings.model import HashEmbeddingModel
from app.llm.base import StaticLLM
from app.rag.generator import RAGGenerator
from app.retrieval.reranker import LexicalReranker
from app.retrieval.retriever import Retriever
from app.validation.schemas import DocumentChunk
from app.vectorstore.faiss_store import NumpyVectorStore
from app.vectorstore.index_manager import IndexManager


def build_agent(tmp_path):
    embedder = HashEmbeddingModel(64)
    store = NumpyVectorStore(64, tmp_path / 'i.npy', tmp_path / 'm.json')
    manager = IndexManager(embedder, store)
    chunks = [
        DocumentChunk(document_id=__import__('uuid').uuid4(), chunk_index=0, text='Employees receive twenty days of annual leave.', metadata={'file_name': 'hr.txt', 'source_path': '/safe/hr.txt'}),
        DocumentChunk(document_id=__import__('uuid').uuid4(), chunk_index=1, text='Python services use typed configuration.', metadata={'file_name': 'engineering.txt', 'source_path': '/safe/engineering.txt'}),
    ]
    manager.add_chunks(chunks)
    retriever = Retriever(manager, LexicalReranker(), -1.0, 0.0)
    tool = RetrievalTool(retriever, 2, 2)
    generator = RAGGenerator(StaticLLM('According to the source, employees receive twenty days of annual leave.'))
    return RAGAgent(QueryRouter(), AgentPlanner(), tool, generator, StaticLLM('Hello!'))


def test_agent_retrieval_flow(tmp_path):
    response = build_agent(tmp_path).run('How many annual leave days do employees receive?')
    assert response.action == 'retrieve'
    assert response.citations
    assert response.confidence >= 0


def test_agent_direct_flow(tmp_path):
    response = build_agent(tmp_path).run('hello')
    assert response.action == 'direct_answer'
    assert response.answer == 'Hello!'


def test_agent_rejects_empty_query(tmp_path):
    import pytest
    from app.core.exceptions import AgentError
    with pytest.raises(AgentError):
        build_agent(tmp_path).run('   ')


def test_agent_low_confidence_verification(tmp_path):
    # Keep the minimum score permissive so the planner can exercise its verification branch.
    response = build_agent(tmp_path).run('annual')
    assert response.action == 'retrieve'
    assert response.citations


def test_agent_uses_follow_up_history_to_improve_retrieval(tmp_path):
    from app.validation.schemas import ChatMessage

    class CapturingRetriever:
        def __init__(self):
            self.query = None

        def run(self, query: str):
            self.query = query
            return query, [], 0.0

    retriever = CapturingRetriever()
    agent = RAGAgent(
        QueryRouter(),
        AgentPlanner(),
        retriever,
        RAGGenerator(StaticLLM("unused")),
        None,
        DocumentAnalysisTool(tmp_path, 25),
    )
    (tmp_path / "sample.txt").write_text("Annual leave policy.", encoding="utf-8")
    agent.run(
        "Who approves it?",
        history=[
            ChatMessage(id="1", role="user", content="What is the annual leave policy?", created_at="now"),
            ChatMessage(id="2", role="assistant", content="Employees receive twenty days of annual leave.", created_at="now"),
        ],
    )
    assert retriever.query is not None
    assert "annual leave policy" in retriever.query.lower()
