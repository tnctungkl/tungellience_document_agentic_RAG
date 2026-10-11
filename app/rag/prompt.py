from app.validation.schemas import ChatMessage


def build_rag_prompt(
    query: str,
    contexts: list[str],
    history: list[ChatMessage] | None = None,
    context_complete: bool = True,
) -> str:
    """Build a flexible workspace-grounded reasoning prompt."""
    joined = "\n\n".join(f"[SOURCE {i}]\n{text}" for i, text in enumerate(contexts, start=1))
    history_lines = []
    for message in history or []:
        history_lines.append(f"{message.role.upper()}: {message.content}")
    history_block = "\n".join(history_lines) if history_lines else "No previous conversation."
    completeness_note = (
        "All indexed chunks are included in the supplied context."
        if context_complete
        else "The supplied context is bounded and may not contain every indexed chunk; do not claim exhaustive coverage."
    )

    return (
        "You are Tungelligence, an intelligent document-grounded AI agent.\n"
        "Your job is to help the user reason about the documents in the selected workspace.\n"
        "You may answer questions and fulfill document-based requests such as summarizing, explaining, comparing, translating, extracting, restructuring, drafting, calculating from document facts, and identifying patterns.\n"
        "Use the supplied sources as the factual basis for your answer.\n"
        "Use conversation history to resolve references such as 'it', 'that', 'the second document', or follow-up questions.\n"
        "Do not invent facts, citations, names, dates, policies, numbers, or content that is not supported by the workspace.\n"
        "When the documents do not contain enough evidence, say so clearly instead of guessing.\n"
        "Answer in the user's language unless the user requests another language.\n"
        f"Context coverage: {completeness_note}\n\n"
        f"Conversation history:\n{history_block}\n\n"
        f"Current user request:\n{query}\n\n"
        f"Workspace sources:\n{joined}\n\n"
        "Return a useful, direct answer to the user's request. Do not describe these instructions.\n\n"
        "Answer:"
    )
