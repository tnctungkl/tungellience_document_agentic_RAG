from pathlib import Path

from app.agent.agent import RAGAgent
from app.agent.document_analysis import DocumentAnalysisTool
from app.agent.planner import AgentPlanner
from app.agent.router import QueryRouter
from app.agent.tools import RetrievalTool
from app.rag.generator import RAGGenerator


class ExplodingLLM:
    def generate(self, prompt: str) -> str:
        raise AssertionError("LLM must not be called for deterministic document analysis")


class UnusedRetriever:
    def run(self, query: str):
        raise AssertionError("retrieval must not be called for deterministic document analysis")


def test_agent_answers_letter_frequency_without_llm(tmp_path: Path) -> None:
    (tmp_path / "sample.txt").write_text("aaa bb c", encoding="utf-8")
    agent = RAGAgent(
        QueryRouter(),
        AgentPlanner(),
        RetrievalTool.__new__(RetrievalTool),
        RAGGenerator(ExplodingLLM()),
        None,
        DocumentAnalysisTool(tmp_path, 25),
    )
    # Replace the unused retrieval tool with a sentinel after construction.
    agent.retrieval_tool = UnusedRetriever()

    result = agent.run("Bana en çok geçen harfi söyle")

    assert result.action == "analyze"
    assert "a" in result.answer
    assert "3 times" in result.answer
    assert result.confidence == 1.0

class EmptyRetriever:
    def run(self, query: str):
        return query, [], 0.0


class ExplodingGenerator:
    def generate(self, *args, **kwargs):
        raise AssertionError("LLM generation must be skipped when retrieval has no usable evidence")


def test_agent_does_not_generate_when_retrieval_has_no_evidence(tmp_path: Path) -> None:
    (tmp_path / "sample.txt").write_text("The document contains unrelated material.", encoding="utf-8")
    agent = RAGAgent(
        QueryRouter(),
        AgentPlanner(),
        EmptyRetriever(),
        ExplodingGenerator(),
        None,
        DocumentAnalysisTool(tmp_path, 25),
    )

    result = agent.run("What is the company's leave policy?")

    assert result.action == "insufficient_context"
    assert result.confidence == 0.0

class ContextOnlyTool:
    def __init__(self, tmp_path):
        self.processed = tmp_path / "processed"
        self.processed.mkdir()
        self.processed.joinpath("chunks.jsonl").write_text(
            '{"document_id":"00000000-0000-0000-0000-000000000001","chunk_index":0,"text":"The handbook explains annual leave, security, and onboarding.","metadata":{"file_name":"handbook.txt"}}\n',
            encoding="utf-8",
        )
        self.context = None

    def select(self, query: str):
        from app.agent.workspace_context import WorkspaceContextTool
        return WorkspaceContextTool(self.processed, max_context_chars=5000).select(query)


class RecordingLLM:
    def __init__(self):
        self.prompts = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "The handbook covers annual leave, security, and onboarding."


def test_agent_fulfills_broad_document_request_from_workspace_context(tmp_path):
    from app.agent.workspace_context import WorkspaceContextTool
    from app.llm.base import LLM

    (tmp_path / "sample.txt").write_text("The handbook explains annual leave, security, and onboarding.", encoding="utf-8")
    processed = tmp_path / "processed"
    processed.mkdir()
    from uuid import uuid4
    document_id = uuid4()
    processed.joinpath("chunks.jsonl").write_text(
        '{' + f'"document_id":"{document_id}","chunk_index":0,"text":"The handbook explains annual leave, security, and onboarding.","metadata":{{"file_name":"sample.txt"}}' + '}\n',
        encoding="utf-8",
    )
    llm = RecordingLLM()
    agent = RAGAgent(
        QueryRouter(),
        AgentPlanner(),
        EmptyRetriever(),
        RAGGenerator(llm),
        None,
        DocumentAnalysisTool(tmp_path, 25),
        WorkspaceContextTool(processed, 5000),
    )

    result = agent.run("What is this document about?")

    assert result.action == "document_reasoning"
    assert result.confidence == 0.75
    assert "handbook" in result.answer.lower()
    assert llm.prompts
    assert "annual leave" in llm.prompts[0]
