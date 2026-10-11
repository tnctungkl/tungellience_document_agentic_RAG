from fastapi.testclient import TestClient

from app.agent.agent import RAGAgent
from app.agent.planner import AgentPlanner
from app.agent.router import QueryRouter
from app.agent.tools import RetrievalTool
from app.llm.base import StaticLLM
from app.rag.generator import RAGGenerator
from app.retrieval.reranker import LexicalReranker
from app.retrieval.retriever import Retriever
from app.embeddings.model import HashEmbeddingModel
from app.vectorstore.faiss_store import NumpyVectorStore
from app.vectorstore.index_manager import IndexManager
from app.api.main import create_app


def test_health_endpoint():
    app = create_app()
    client = TestClient(app)
    assert client.get('/health').status_code == 200


def test_query_endpoint_with_injected_agent(tmp_path):
    embedder = HashEmbeddingModel(32)
    store = NumpyVectorStore(32, tmp_path / 'i.npy', tmp_path / 'm.json')
    manager = IndexManager(embedder, store)
    from app.validation.schemas import DocumentChunk
    from uuid import uuid4
    chunk = DocumentChunk(document_id=uuid4(), chunk_index=0, text='The system uses Docker.', metadata={'file_name': 'ops.txt', 'source_path': '/safe/ops.txt'})
    manager.add_chunks([chunk])
    retriever = Retriever(manager, LexicalReranker(), -1.0, 0.0)
    agent = RAGAgent(QueryRouter(), AgentPlanner(), RetrievalTool(retriever, 1, 1), RAGGenerator(StaticLLM('Docker is used.')), StaticLLM('Hello!'))
    client = TestClient(create_app(agent))
    response = client.post('/v1/query', json={'query': 'Does the system use Docker?'})
    assert response.status_code == 200
    assert response.json()['answer'] == 'Docker is used.'


def test_report_endpoint_returns_pdf():
    payload = {
        "response": {
            "answer": "Türkçe cevap: çalışma politikası.",
            "action": "retrieve",
            "query": "Bu doküman ne anlatıyor?",
            "rewritten_query": None,
            "confidence": 0.91,
            "citations": [],
        }
    }
    client = TestClient(create_app())
    response = client.post("/v1/report", json=payload)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.content.startswith(b"%PDF")


def test_report_endpoint_rejects_empty_answer():
    payload = {
        "response": {
            "answer": "   ",
            "action": "retrieve",
            "query": "test",
            "rewritten_query": None,
            "confidence": 0.0,
            "citations": [],
        }
    }
    client = TestClient(create_app())
    response = client.post("/v1/report", json=payload)

    assert response.status_code == 400



def test_workspace_query_maps_generation_failure_to_503(monkeypatch, tmp_path):
    from app.core.exceptions import GenerationError
    from app.core.config import get_settings
    from app.workspaces.store import WorkspaceStore

    settings = get_settings()
    store = WorkspaceStore(tmp_path / 'test.db', tmp_path / 'workspaces')
    app = create_app(workspace_store=store)
    client = TestClient(app)

    workspace = client.post('/v1/workspaces', json={'name': 'LLM Failure Test'}).json()
    conversation = client.post(
        f"/v1/workspaces/{workspace['id']}/conversations",
        json={'title': 'Test'},
    ).json()
    # The API checks document_count before building the agent. Stub the store
    # count so this test isolates the model-generation failure mapping.
    monkeypatch.setattr(store, 'document_count', lambda workspace_id: 1)

    class FailingAgent:
        def run(self, *args, **kwargs):
            raise GenerationError('Cannot connect to Ollama')

    monkeypatch.setattr('app.api.main.build_workspace_agent', lambda *args, **kwargs: FailingAgent())

    response = client.post(
        f"/v1/workspaces/{workspace['id']}/conversations/{conversation['id']}/query",
        json={'query': 'Summarize the document.'},
    )

    assert response.status_code == 503
    assert 'Cannot connect to Ollama' in response.json()['detail']
    assert response.headers['retry-after'] == '5'
