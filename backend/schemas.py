from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    """Request payload for creating a new chat session."""

    title: Optional[str] = Field(default="New Chat", description="Optional title for the chat session")


class UpdateSessionRequest(BaseModel):
    """Request payload for renaming an existing chat session."""

    title: str = Field(..., min_length=1, description="New title for the chat session")


class SessionSummary(BaseModel):
    """Summary metadata for a single chat session in the session list."""

    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0
    last_message: Optional[str] = None


class ChatMessageItem(BaseModel):
    """Single message record within a chat session conversation history."""

    id: int
    session_id: str
    role: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


class SessionDetail(BaseModel):
    """Full chat session metadata including ordered message history."""

    id: str
    title: str
    created_at: str
    updated_at: str
    messages: List[ChatMessageItem] = Field(default_factory=list)


class QueryRequest(BaseModel):
    """Request payload for natural language queries."""

    query: str
    session_id: Optional[str] = None


class QueryResponse(BaseModel):
    """Response payload returned after processing a natural language query."""

    response: str
    metadata: Dict[str, Any]
    session_id: Optional[str] = None
    trace_id: Optional[str] = None


class IngestFileResponse(BaseModel):
    """Response payload returned after uploading and ingesting a tabular file."""

    status: str
    session_id: Optional[str] = None
    table_names: List[str] = Field(default_factory=list)
    tables: List[Dict[str, Any]] = Field(default_factory=list)
    questions: List[Dict[str, Any]] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    message: str
