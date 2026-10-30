from datetime import datetime
from functools import lru_cache
import json
import logging
import os
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from sqlalchemy import Engine, text

from agents.db_agent.config import get_settings as get_db_settings
from agents.db_agent.db import create_db_engine

load_dotenv()

logger = logging.getLogger("backend.database")


@lru_cache(maxsize=1)
def get_db() -> Engine:
    """Returns the cached SQLAlchemy database engine."""
    db_cfg = get_db_settings()
    return create_db_engine(db_cfg.database_url)


def get_ai_service_url() -> str:
    """Returns the base URL of the AI orchestration service."""
    return os.getenv("AI_SERVICE_URL", "http://ai:8001").rstrip("/")


def parse_json_metadata(raw_meta: Any) -> Dict[str, Any]:
    """Parses a raw database JSONB or string metadata column into a dictionary."""
    if isinstance(raw_meta, dict):
        return raw_meta
    if isinstance(raw_meta, str):
        try:
            parsed = json.loads(raw_meta)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}


def ensure_session_record(engine: Engine, session_id: str, title: str = "New Chat") -> None:
    """Ensures a chat session row exists in internal.chat_sessions."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO internal.chat_sessions (id, title) "
                "VALUES (:id, :title) ON CONFLICT (id) DO NOTHING"
            ),
            {"id": session_id, "title": title},
        )


def save_chat_message(
    engine: Engine,
    session_id: str,
    role: str,
    content: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> datetime:
    """
    Persists a message in internal.chat_messages and updates the session timestamp.

    Args:
        engine (Engine): SQLAlchemy database engine.
        session_id (str): Target chat session identifier.
        role (str): Message author role ('user' or 'assistant').
        content (str): Markdown text content of the message.
        metadata (Optional[Dict[str, Any]]): Optional structured metadata payload.

    Returns:
        datetime: Timestamp recorded for the persisted message.
    """
    now = datetime.now()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO internal.chat_messages (session_id, role, content, metadata, created_at)
                VALUES (:sid, :role, :content, :meta, :now)
                """
            ),
            {
                "sid": session_id,
                "role": role,
                "content": content,
                "meta": json.dumps(metadata or {}),
                "now": now,
            },
        )
        conn.execute(
            text("UPDATE internal.chat_sessions SET updated_at = :now WHERE id = :sid"),
            {"sid": session_id, "now": now},
        )
    return now
