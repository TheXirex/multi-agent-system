from datetime import datetime
import logging
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from backend.database import get_db, parse_json_metadata
from backend.schemas import (
    ChatMessageItem,
    CreateSessionRequest,
    SessionDetail,
    SessionSummary,
    UpdateSessionRequest,
)
from shared.db import drop_session_replica, ensure_session_replica

logger = logging.getLogger("backend.routes.sessions")

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=List[SessionSummary])
@router.get("/", response_model=List[SessionSummary])
async def list_sessions() -> List[SessionSummary]:
    """Returns all chat sessions ordered by most recently updated."""
    engine = get_db()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT s.id, s.title, s.created_at, s.updated_at,
                       COUNT(m.id) AS message_count,
                       (SELECT content FROM internal.chat_messages WHERE session_id = s.id ORDER BY id DESC LIMIT 1) AS last_msg
                FROM internal.chat_sessions s
                LEFT JOIN internal.chat_messages m ON s.id = m.session_id
                GROUP BY s.id, s.title, s.created_at, s.updated_at
                ORDER BY s.updated_at DESC
                """
            )
        ).fetchall()

    return [
        SessionSummary(
            id=str(r[0]),
            title=str(r[1]),
            created_at=str(r[2]),
            updated_at=str(r[3]),
            message_count=int(r[4] or 0),
            last_message=str(r[5])[:80] if r[5] else None,
        )
        for r in rows
    ]


@router.post("", response_model=SessionSummary)
@router.post("/", response_model=SessionSummary)
async def create_session(req: Optional[CreateSessionRequest] = None) -> SessionSummary:
    """Creates a new chat session and initializes its PostgreSQL schema replica."""
    engine = get_db()
    new_id = str(uuid.uuid4())
    title = (req.title if req and req.title else "New Chat").strip() or "New Chat"
    now = datetime.now()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO internal.chat_sessions (id, title, created_at, updated_at) "
                "VALUES (:id, :title, :now, :now)"
            ),
            {"id": new_id, "title": title, "now": now},
        )
    ensure_session_replica(engine, new_id)
    return SessionSummary(
        id=new_id,
        title=title,
        created_at=str(now),
        updated_at=str(now),
        message_count=0,
        last_message=None,
    )


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str) -> SessionDetail:
    """Retrieves full metadata and ordered message history for a chat session."""
    engine = get_db()
    with engine.connect() as conn:
        s_row = conn.execute(
            text("SELECT id, title, created_at, updated_at FROM internal.chat_sessions WHERE id = :id"),
            {"id": session_id},
        ).fetchone()

        if not s_row:
            raise HTTPException(status_code=404, detail="Session not found")

        m_rows = conn.execute(
            text(
                "SELECT id, session_id, role, content, metadata, created_at "
                "FROM internal.chat_messages WHERE session_id = :id ORDER BY id ASC"
            ),
            {"id": session_id},
        ).fetchall()

    messages = [
        ChatMessageItem(
            id=mr[0],
            session_id=str(mr[1]),
            role=str(mr[2]),
            content=str(mr[3]),
            metadata=parse_json_metadata(mr[4]),
            created_at=str(mr[5]),
        )
        for mr in m_rows
    ]

    return SessionDetail(
        id=str(s_row[0]),
        title=str(s_row[1]),
        created_at=str(s_row[2]),
        updated_at=str(s_row[3]),
        messages=messages,
    )


@router.delete("/{session_id}")
async def delete_session(session_id: str) -> Dict[str, Any]:
    """Deletes a session, its artifacts, change history, and dedicated schema replica."""
    engine = get_db()
    drop_session_replica(engine, session_id)

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM internal.generated_charts WHERE session_id = :id"),
            {"id": session_id},
        )
        conn.execute(
            text("DELETE FROM internal.generated_scripts WHERE session_id = :id"),
            {"id": session_id},
        )
        conn.execute(
            text("DELETE FROM internal.change_history WHERE session_id = :id"),
            {"id": session_id},
        )
        conn.execute(
            text("DELETE FROM internal.chat_sessions WHERE id = :id"),
            {"id": session_id},
        )
    return {"status": "deleted", "session_id": session_id}


@router.patch("/{session_id}")
async def update_session_title(session_id: str, req: UpdateSessionRequest) -> Dict[str, Any]:
    """Updates the title of an existing chat session."""
    new_title = req.title.strip()
    if not new_title:
        raise HTTPException(status_code=400, detail="Title cannot be empty")

    engine = get_db()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE internal.chat_sessions SET title = :title, updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
            {"id": session_id, "title": new_title},
        )
    return {"status": "updated", "session_id": session_id, "title": new_title}
