class RAGApplicationError(Exception):
    """Base exception for application-level errors."""


class ConfigurationError(RAGApplicationError):
    """Raised when application configuration is invalid."""


class IngestionError(RAGApplicationError):
    """Raised when document ingestion fails."""


class ProcessingError(RAGApplicationError):
    """Raised when document processing fails."""


class EmbeddingError(RAGApplicationError):
    """Raised when embedding generation fails."""


class VectorStoreError(RAGApplicationError):
    """Raised when vector store operations fail."""


class RetrievalError(RAGApplicationError):
    """Raised when retrieval fails."""


class GenerationError(RAGApplicationError):
    """Raised when LLM generation fails."""


class AgentError(RAGApplicationError):
    """Raised when agent orchestration fails."""
