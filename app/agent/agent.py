from __future__ import annotations

from app.agent.document_analysis import DocumentAnalysisTool
from app.agent.planner import AgentPlanner
from app.agent.router import QueryRouter
from app.agent.state import AgentState
from app.agent.tools import RetrievalTool
from app.agent.workspace_context import WorkspaceContextTool
from app.core.exceptions import AgentError, RAGApplicationError
from app.llm.base import LLM
from app.rag.citation import build_citations
from app.rag.generator import RAGGenerator
from app.validation.schemas import AgentResponse, ChatMessage, Citation, SearchResult


class RAGAgent:
    """Workspace-grounded agent that can reason over documents and use deterministic tools."""

    def __init__(
        self,
        router: QueryRouter,
        planner: AgentPlanner,
        retrieval_tool: RetrievalTool,
        generator: RAGGenerator,
        direct_llm: LLM | None,
        analysis_tool: DocumentAnalysisTool | None = None,
        context_tool: WorkspaceContextTool | None = None,
    ) -> None:
        self.router = router
        self.planner = planner
        self.retrieval_tool = retrieval_tool
        self.generator = generator
        self.direct_llm = direct_llm
        self.analysis_tool = analysis_tool
        self.context_tool = context_tool

    def run(
        self,
        query: str,
        history: list[ChatMessage] | None = None,
        knowledge_available: bool = True,
    ) -> AgentResponse:
        state = AgentState(query=query.strip())
        if not state.query:
            raise AgentError("query cannot be empty")
        if not knowledge_available:
            raise AgentError("workspace has no indexed documents")

        analysis_supported = bool(self.analysis_tool and self.analysis_tool.supports(state.query))
        state.action = self.router.route(state.query, analysis_supported=analysis_supported)

        if state.action == "direct_answer":
            # Keep greetings deterministic and token-free.
            answer = (
                self.direct_llm.generate(state.query).strip()
                if self.direct_llm
                else "Hello. I am ready to work with the documents in this workspace."
            )
            return AgentResponse(answer=answer, action=state.action, query=state.query, confidence=1.0)

        if state.action == "analyze":
            assert self.analysis_tool is not None
            try:
                result = self.analysis_tool.analyze(state.query)
            except RAGApplicationError:
                raise
            if result is None:
                raise AgentError("analysis request could not be resolved")
            citations = [Citation(source=source, chunk_id="document", score=1.0) for source in result.sources]
            return AgentResponse(
                answer=result.answer,
                action="analyze",
                query=state.query,
                citations=citations,
                confidence=1.0,
            )

        retrieval_query = self._build_retrieval_query(state.query, history)
        rewritten, results, confidence = self.retrieval_tool.run(retrieval_query)
        state.rewritten_query = rewritten
        state.results = results
        state.confidence = confidence

        planned = self.planner.next_action(state)
        if planned == "verify" and state.results:
            rewritten, results, confidence = self.retrieval_tool.run(rewritten)
            state.rewritten_query = rewritten
            state.results = results
            state.confidence = confidence

        if state.results and state.confidence >= self.planner.min_generation_confidence:
            answer = self.generator.generate(state.query, state.results, history)
            return AgentResponse(
                answer=answer,
                action="retrieve",
                query=state.query,
                rewritten_query=state.rewritten_query,
                citations=build_citations(state.results),
                confidence=state.confidence,
            )

        # Retrieval can be weak for broad requests such as summaries, translations, comparisons,
        # and "what is inside this file?". Fall back to bounded workspace context instead of giving
        # a useless canned response, while still grounding every factual claim in the documents.
        if self.context_tool is not None:
            context_items, context_complete = self.context_tool.select(state.query)
            if context_items:
                contexts = [item.chunk.text for item in context_items]
                answer = self.generator.generate_from_context(state.query, contexts, history, context_complete)
                citations = [
                    Citation(
                        source=item.chunk.metadata.get("file_name", "unknown"),
                        chunk_id=str(item.chunk.id),
                        score=min(1.0, 0.50 + item.score / 10.0),
                    )
                    for item in context_items
                ]
                return AgentResponse(
                    answer=answer,
                    action="document_reasoning",
                    query=state.query,
                    rewritten_query=state.rewritten_query,
                    citations=citations,
                    confidence=0.75 if context_complete else 0.60,
                )

        # Never send a generation request without usable workspace evidence.
        return AgentResponse(
            answer="I could not find enough relevant information in this workspace to answer that question.",
            action="insufficient_context",
            query=state.query,
            rewritten_query=state.rewritten_query,
            citations=build_citations(state.results),
            confidence=state.confidence,
        )

    @staticmethod
    def _build_retrieval_query(query: str, history: list[ChatMessage] | None) -> str:
        """Add minimal recent context to improve retrieval for conversational follow-ups."""
        recent_user = next((message.content for message in reversed(history or []) if message.role == "user"), "")
        if recent_user and recent_user.strip() != query.strip():
            return f"{recent_user[:600]} {query[:1200]}"
        return query
