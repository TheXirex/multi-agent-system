"""
HTTP API backend service package for the Multi-Agent System.
"""
from backend.app import app, create_app, lifespan
from backend.database import get_db
from backend.schemas import (
    AttachedFileItem,
    ChatMessageItem,
    CreateSessionRequest,
    IngestFileResponse,
    QueryRequest,
    QueryResponse,
    SessionDetail,
    SessionSummary,
    UpdateSessionRequest,
)

__all__ = [
    "app",
    "create_app",
    "lifespan",
    "get_db",
    "CreateSessionRequest",
    "UpdateSessionRequest",
    "SessionSummary",
    "ChatMessageItem",
    "SessionDetail",
    "AttachedFileItem",
    "QueryRequest",
    "QueryResponse",
    "IngestFileResponse",
]
