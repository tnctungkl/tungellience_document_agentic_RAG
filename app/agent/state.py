from dataclasses import dataclass, field

from app.validation.schemas import SearchResult


@dataclass
class AgentState:
    """Mutable state passed through one agent execution."""

    query: str
    rewritten_query: str | None = None
    action: str = "retrieve"
    results: list[SearchResult] = field(default_factory=list)
    confidence: float = 0.0
