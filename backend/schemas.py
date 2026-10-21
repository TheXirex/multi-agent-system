from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    title: Optional[str] = Field(default="New Chat", description="Optional title for the chat session")


class UpdateSessionRequest(BaseModel):
    title: str = Field(..., min_length=1, description="New title for the chat session")


class SessionSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0
    last_message: Optional[str] = None


class ChatMessageItem(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


class SessionDetail(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    messages: List[ChatMessageItem] = Field(default_factory=list)


class AttachedFileItem(BaseModel):
    filename: str
    content_base64: str


class QueryRequest(BaseModel):
    query: Optional[str] = None
    session_id: Optional[str] = None
    attachments: Optional[List[AttachedFileItem]] = None


class QueryResponse(BaseModel):
    response: str
    metadata: Dict[str, Any]
    session_id: Optional[str] = None


class IngestFileResponse(BaseModel):
    status: str
    session_id: Optional[str] = None
    primary_dataset_id: Optional[int] = None
    dataset_ids: List[int] = Field(default_factory=list)
    datasets: List[Dict[str, Any]] = Field(default_factory=list)
    message: str
