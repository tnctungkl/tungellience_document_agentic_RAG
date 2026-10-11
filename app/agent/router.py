import re


class QueryRouter:
    """Route trivial, deterministic analysis, and retrieval requests."""

    _DIRECT = re.compile(r"^(hi|hello|hey|thanks|thank you|who are you)\b", re.IGNORECASE)

    def route(self, query: str, analysis_supported: bool = False) -> str:
        if self._DIRECT.search(query.strip()):
            return "direct_answer"
        if analysis_supported:
            return "analyze"
        return "retrieve"
