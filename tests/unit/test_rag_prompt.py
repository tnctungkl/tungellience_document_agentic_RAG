from app.rag.prompt import build_rag_prompt
from app.validation.schemas import ChatMessage


def test_prompt_supports_general_document_requests_and_history() -> None:
    prompt = build_rag_prompt(
        "Summarize the document",
        ["Annual leave is 20 days."],
        [ChatMessage(id="1", role="user", content="What does this cover?", created_at="now")],
        context_complete=True,
    )
    assert "summarizing" in prompt.lower() or "summarize" in prompt.lower()
    assert "What does this cover?" in prompt
    assert "Annual leave is 20 days." in prompt
    assert "Answer in the user's language" in prompt
