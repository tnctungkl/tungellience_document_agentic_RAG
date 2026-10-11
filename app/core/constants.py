from enum import StrEnum


class Environment(StrEnum):
    """Supported runtime environments."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class DocumentType(StrEnum):
    """Supported document formats."""

    TXT = "txt"
    MD = "md"
    MARKDOWN = "markdown"
    PDF = "pdf"
    DOCX = "docx"


class AgentAction(StrEnum):
    """Actions available to the agent controller."""

    DIRECT_ANSWER = "direct_answer"
    ANALYZE = "analyze"
    INSUFFICIENT_CONTEXT = "insufficient_context"
    RETRIEVE = "retrieve"
    REWRITE_QUERY = "rewrite_query"
    VERIFY = "verify"
