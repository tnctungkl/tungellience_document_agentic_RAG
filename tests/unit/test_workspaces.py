from pathlib import Path
from uuid import uuid4

import pytest

from app.agent.agent import RAGAgent
from app.agent.planner import AgentPlanner
from app.agent.router import QueryRouter
from app.agent.tools import RetrievalTool
from app.llm.base import StaticLLM
from app.rag.generator import RAGGenerator
from app.rag.prompt import build_rag_prompt
from app.validation.schemas import AgentResponse, ChatMessage, Citation
from app.workspaces.store import WorkspaceStore


class ExplodingRetriever:
    def run(self, query: str):
        raise AssertionError("retrieval must not run in a prompt-only unit test")


def test_workspace_persistence_and_conversation_history(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "app.db", tmp_path / "workspaces")
    workspace = store.create_workspace("Project Alpha")
    conversations = store.list_conversations(workspace["id"])
    assert len(conversations) == 1

    response = AgentResponse(answer="The policy is 20 days.", action="retrieve", query="How many days?", confidence=0.91)
    store.add_turn(workspace["id"], conversations[0]["id"], "How many days?", response.model_dump(mode="json"))
    messages = store.list_messages(workspace["id"], conversations[0]["id"], limit=20)

    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[-1]["response"]["answer"] == "The policy is 20 days."


def test_workspace_delete_isolated(tmp_path: Path) -> None:
    store = WorkspaceStore(tmp_path / "app.db", tmp_path / "workspaces")
    first = store.create_workspace("One")
    second = store.create_workspace("Two")
    store.delete_workspace(first["id"])

    ids = {item["id"] for item in store.list_workspaces()}
    assert first["id"] not in ids
    assert second["id"] in ids
    assert not (tmp_path / "workspaces" / first["id"]).exists()


def test_prompt_includes_recent_history() -> None:
    history = [
        ChatMessage(id=str(uuid4()), role="user", content="What is annual leave?", created_at="2026-01-01T00:00:00Z"),
        ChatMessage(id=str(uuid4()), role="assistant", content="It is 20 days.", created_at="2026-01-01T00:00:01Z"),
    ]
    prompt = build_rag_prompt("Can you explain who approves it?", ["Managers approve leave requests."], history)
    assert "USER: What is annual leave?" in prompt
    assert "ASSISTANT: It is 20 days." in prompt
    assert "Managers approve leave requests." in prompt


def test_agent_refuses_without_knowledge() -> None:
    agent = RAGAgent(QueryRouter(), AgentPlanner(), ExplodingRetriever(), RAGGenerator(StaticLLM("should not run")), None)
    with pytest.raises(Exception, match="no indexed documents"):
        agent.run("Hello", knowledge_available=False)

class StubRetriever:
    def run(self, query: str):
        from app.validation.schemas import DocumentChunk, SearchResult
        from app.validation.schemas import Document
        chunk = DocumentChunk(document_id=uuid4(), chunk_index=0, text="Managers approve leave requests.")
        return query, [SearchResult(chunk=chunk, vector_score=0.95, rerank_score=0.95)], 0.95


class RecordingLLM(StaticLLM):
    def __init__(self):
        super().__init__("Managers approve leave requests.")
        self.prompt = ""

    def generate(self, prompt: str) -> str:
        self.prompt = prompt
        return self.response


def test_agent_passes_history_to_generator() -> None:
    llm = RecordingLLM()
    agent = RAGAgent(QueryRouter(), AgentPlanner(), StubRetriever(), RAGGenerator(llm), None)
    history = [ChatMessage(id=str(uuid4()), role="user", content="What is annual leave?", created_at="2026-01-01T00:00:00Z")]
    agent.run("Who approves it?", history=history, knowledge_available=True)
    assert "USER: What is annual leave?" in llm.prompt


def test_hash_numpy_index_build_is_functional(tmp_path: Path, monkeypatch) -> None:
    from app.core.config import Settings
    from app.workspaces.indexing import rebuild_workspace_index

    settings = Settings(
        embedding_provider='hash',
        vector_store_backend='numpy',
        embedding_dimension=128,
        workspace_data_dir=tmp_path / 'workspaces',
        workspace_db_path=tmp_path / 'app.db',
        raw_data_dir=tmp_path / 'raw',
        processed_data_dir=tmp_path / 'processed',
        vector_data_dir=tmp_path / 'vector',
    )
    store = WorkspaceStore(settings.workspace_db_path, settings.workspace_data_dir)
    workspace = store.create_workspace('Offline')
    raw_dir = store.raw_dir(workspace['id'])
    (raw_dir / 'policy.md').write_text('# Policy\nEmployees receive 20 days of annual leave.', encoding='utf-8')

    docs = rebuild_workspace_index(workspace['id'], store, settings)
    assert docs[0]['file_name'] == 'policy.md'
    assert docs[0]['chunk_count'] >= 1
    assert (store.vector_dir(workspace['id']) / 'index.npy').exists()
    assert (store.vector_dir(workspace['id']) / 'chunks.json').exists()

    from app.vectorstore.faiss_store import NumpyVectorStore
    store_backend = NumpyVectorStore(128, store.vector_dir(workspace['id']) / 'index.npy', store.vector_dir(workspace['id']) / 'chunks.json')
    store_backend.load()
    assert store_backend.size >= 1
