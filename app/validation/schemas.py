from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Document(BaseModel):
    """Normalized source document."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    source_path: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    document_type: str = Field(min_length=1)
    content: str = Field(min_length=1)
    metadata: dict[str, str] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must contain non-whitespace text")
        return value


class DocumentChunk(BaseModel):
    """Deterministic chunk used for embedding and retrieval."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    document_id: UUID
    chunk_index: int = Field(ge=0)
    text: str = Field(min_length=1)
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("chunk text must contain non-whitespace text")
        return value


class SearchResult(BaseModel):
    """A retrieved chunk with vector and reranking scores."""

    model_config = ConfigDict(extra="forbid")

    chunk: DocumentChunk
    vector_score: float
    rerank_score: float | None = None


class QueryRequest(BaseModel):
    """API request for an agentic question-answering operation."""

    query: str = Field(min_length=1, max_length=4000)
    top_k: int | None = Field(default=None, ge=1, le=20)


class Citation(BaseModel):
    """Source citation exposed to API/UI clients."""

    source: str
    chunk_id: str
    score: float


class AgentResponse(BaseModel):
    """Final agent response and trace-friendly retrieval metadata."""

    answer: str
    action: str
    query: str
    rewritten_query: str | None = None
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class ReportRequest(BaseModel):
    """Request containing a completed response eligible for PDF export."""

    response: AgentResponse

class WorkspaceCreateRequest(BaseModel):
    """Create a named workspace."""

    name: str = Field(min_length=1, max_length=80)


class WorkspaceRenameRequest(BaseModel):
    """Rename an existing workspace."""

    name: str = Field(min_length=1, max_length=80)


class WorkspaceSummary(BaseModel):
    """Workspace data exposed to the UI."""

    id: str
    name: str
    created_at: str
    updated_at: str
    document_count: int
    conversation_count: int


class ConversationCreateRequest(BaseModel):
    """Create a new conversation inside a workspace."""

    title: str = Field(default="New conversation", min_length=1, max_length=120)


class ConversationSummary(BaseModel):
    """Conversation summary shown in the workspace sidebar."""

    id: str
    workspace_id: str
    title: str
    created_at: str
    updated_at: str


class ChatMessage(BaseModel):
    """One persisted chat message."""

    id: str
    role: str
    content: str
    created_at: str
    response: AgentResponse | None = None


class DocumentSummary(BaseModel):
    """Indexed source document summary."""

    id: str
    file_name: str
    size_bytes: int
    chunk_count: int
    indexed_at: str


class DocumentDeleteRequest(BaseModel):
    """Request to permanently remove one or more indexed documents."""

    document_ids: list[str] = Field(min_length=1, max_length=100)


class DocumentDeleteResponse(BaseModel):
    """Result of a document deletion operation."""

    deleted_count: int = Field(ge=1)
    deleted_files: list[str] = Field(min_length=1)
    documents: list[DocumentSummary] = Field(default_factory=list)


class WorkspaceState(BaseModel):
    """Current workspace state needed by the web client."""

    workspace: WorkspaceSummary
    conversations: list[ConversationSummary]
    documents: list[DocumentSummary]


class QueryResponseEnvelope(BaseModel):
    """Chat response including its persisted response and conversation id."""

    conversation_id: str
    response: AgentResponse

