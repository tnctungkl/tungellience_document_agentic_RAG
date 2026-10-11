from app.core.exceptions import GenerationError
from app.llm.base import LLM
from app.rag.prompt import build_rag_prompt
from app.validation.schemas import ChatMessage, SearchResult


class RAGGenerator:
    """Generate flexible, grounded answers from retrieved or bounded workspace context."""

    def __init__(self, llm: LLM) -> None:
        self.llm = llm

    def generate(self, query: str, results: list[SearchResult], history: list[ChatMessage] | None = None) -> str:
        if not results:
            # Preserve a deterministic compatibility response without invoking the LLM.
            return "I could not find enough relevant information in this workspace to answer the question."
        return self.generate_from_context(
            query,
            [result.chunk.text for result in results],
            history,
            context_complete=False,
        )

    def generate_from_context(
        self,
        query: str,
        contexts: list[str],
        history: list[ChatMessage] | None = None,
        context_complete: bool = True,
    ) -> str:
        if not contexts:
            raise GenerationError("cannot generate without workspace context")
        prompt = build_rag_prompt(query, contexts, history, context_complete=context_complete)
        answer = self.llm.generate(prompt).strip()
        if not answer:
            raise GenerationError("generator returned an empty answer")
        return answer
