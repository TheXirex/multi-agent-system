import base64
from datetime import datetime
import json
import logging
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

import os
import httpx
from agents.db_agent.tools import IngestTabularFileTool
from backend.database import get_db
from backend.schemas import QueryRequest, QueryResponse

logger = logging.getLogger("backend.routes.query")

router = APIRouter(tags=["query"])

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://ai:8001").rstrip("/")


def truncate_to_nearest_space(text: str, limit: int = 45) -> str:
    """
    Truncates text to the nearest whitespace before the specified character limit,
    avoiding cutting words in half.
    """
    clean = text.strip()
    if len(clean) <= limit:
        return clean

    sliced = clean[:limit]
    last_space = sliced.rfind(" ")
    if last_space > 0:
        return f"{sliced[:last_space].rstrip()}..."
    return f"{sliced.rstrip()}..."


@router.post("/api/query", response_model=QueryResponse)
@router.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest) -> QueryResponse:
    """
    Primary endpoint for natural language queries and attached dataset processing:
    Binds any attached files exclusively to the target session_id,
    maintains conversational memory and active session metadata in PostgreSQL,
    runs Orchestrator agent to process query, and persists message turns.
    """
    raw_query = (request.query or "").strip()
    if not raw_query and not request.attachments:
        raise HTTPException(status_code=400, detail="Query or file attachment must be provided.")

    engine = get_db()
    session_id = request.session_id

    # 1. Ensure session exists or create a new one FIRST so attachments are strictly bound to it
    with engine.begin() as conn:
        if session_id:
            exists = conn.execute(
                text("SELECT 1 FROM internal.chat_sessions WHERE id = :id"),
                {"id": session_id},
            ).scalar()
            if not exists:
                conn.execute(
                    text("INSERT INTO internal.chat_sessions (id, title) VALUES (:id, 'New Chat')"),
                    {"id": session_id},
                )
        else:
            session_id = str(uuid.uuid4())
            conn.execute(
                text("INSERT INTO internal.chat_sessions (id, title) VALUES (:id, 'New Chat')"),
                {"id": session_id},
            )

    # 2. Ingest any pending attachments and bind them specifically to this session
    attached_dataset_ids: List[int] = []
    attachment_summaries: List[Dict[str, Any]] = []

    if request.attachments:
        ingest_tool = IngestTabularFileTool(engine=engine)
        for att in request.attachments:
            try:
                file_bytes = base64.b64decode(att.content_base64)
                ingest_res = ingest_tool.execute(
                    file_bytes=file_bytes,
                    filename=att.filename,
                    session_id=session_id,
                )
                if ingest_res.get("status") == "success":
                    p_id = ingest_res.get("primary_dataset_id")
                    if p_id:
                        attached_dataset_ids.append(p_id)
                    all_ids = ingest_res.get("dataset_ids", [])
                    for d_id in all_ids:
                        if d_id not in attached_dataset_ids:
                            attached_dataset_ids.append(d_id)

                    attachment_summaries.append({
                        "filename": att.filename,
                        "primary_dataset_id": p_id,
                        "dataset_ids": all_ids,
                    })
                    logger.info(f"Ingested attachment '{att.filename}' for session {session_id} -> dataset_ids={all_ids}")
            except Exception as e:
                logger.error(f"Error ingesting attachment {att.filename}: {e}")

    # Build effective query string
    if not raw_query and attachment_summaries:
        file_names = ", ".join(f"`{a['filename']}`" for a in attachment_summaries)
        effective_query = f"I have uploaded {file_names} (Dataset IDs: {attached_dataset_ids}). Please provide an overview and summary of this data."
    else:
        effective_query = raw_query

    # 3. Retrieve conversation history for this session from PostgreSQL
    history: List[Dict[str, Any]] = []
    active_metadata: Dict[str, Any] = {}
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT role, content, metadata
                FROM internal.chat_messages
                WHERE session_id = :sid
                ORDER BY id ASC
            """),
            {"sid": session_id},
        ).fetchall()

        for r in rows:
            history.append({"role": r[0], "content": r[1]})
            meta_val = r[2]
            if isinstance(meta_val, str):
                try:
                    meta_val = json.loads(meta_val)
                except Exception:
                    meta_val = {}
            if isinstance(meta_val, dict) and meta_val:
                active_metadata.update(meta_val)

    # Inject newly attached dataset IDs into active metadata and context
    active_metadata["session_id"] = session_id
    if attached_dataset_ids:
        active_metadata["dataset_id"] = attached_dataset_ids[0]
        active_metadata["dataset_ids"] = attached_dataset_ids
        logger.info(f"Session {session_id} active metadata updated with dataset IDs: {attached_dataset_ids}")

    # 4. Save User Message into PostgreSQL
    user_metadata: Dict[str, Any] = {}
    if request.attachments:
        user_metadata["attachments"] = [
            {"filename": a.filename, "dataset_ids": attached_dataset_ids}
            for a in request.attachments
        ]

    now_user = datetime.now()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO internal.chat_messages (session_id, role, content, metadata, created_at)
                VALUES (:sid, 'user', :content, :meta, :now)
            """),
            {
                "sid": session_id,
                "content": effective_query,
                "meta": json.dumps(user_metadata),
                "now": now_user,
            },
        )
        conn.execute(
            text("UPDATE internal.chat_sessions SET updated_at = :now WHERE id = :sid"),
            {"sid": session_id, "now": now_user},
        )

    # 5. Forward request to AI Multi-Agent Service
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            ai_resp = await client.post(
                f"{AI_SERVICE_URL}/process",
                json={
                    "query": effective_query,
                    "history": history,
                    "active_metadata": active_metadata,
                    "session_id": session_id,
                },
            )
            if ai_resp.status_code != 200:
                logger.error(f"AI service returned error {ai_resp.status_code}: {ai_resp.text}")
                raise HTTPException(
                    status_code=502,
                    detail=f"AI service error: {ai_resp.text}",
                )
            ai_data = ai_resp.json()
    except httpx.RequestError as exc:
        logger.error(f"Failed to communicate with AI service at {AI_SERVICE_URL}: {exc}")
        raise HTTPException(
            status_code=503,
            detail=f"AI service is unreachable at {AI_SERVICE_URL}: {exc}",
        )

    ai_response_text = ai_data.get("response", "")
    resp_metadata = dict(ai_data.get("metadata", {}))

    # Ensure returned metadata reflects session_id and attached datasets
    resp_metadata["session_id"] = session_id
    if attached_dataset_ids and not resp_metadata.get("dataset_id"):
        resp_metadata["dataset_id"] = attached_dataset_ids[0]
        resp_metadata["dataset_ids"] = attached_dataset_ids

    # 6. Save Assistant Response into PostgreSQL
    now_asst = datetime.now()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO internal.chat_messages (session_id, role, content, metadata, created_at)
                VALUES (:sid, 'assistant', :content, :meta, :now)
            """),
            {
                "sid": session_id,
                "content": ai_response_text,
                "meta": json.dumps(resp_metadata),
                "now": now_asst,
            },
        )

        # Automatically update session title if this was the first query
        first_count = conn.execute(
            text("SELECT COUNT(*) FROM internal.chat_messages WHERE session_id = :sid AND role = 'user'"),
            {"sid": session_id},
        ).scalar()
        if first_count == 1:
            title_sample = truncate_to_nearest_space(effective_query, limit=45)
            conn.execute(
                text("UPDATE internal.chat_sessions SET title = :title, updated_at = :now WHERE id = :sid"),
                {"sid": session_id, "title": title_sample, "now": now_asst},
            )
        else:
            conn.execute(
                text("UPDATE internal.chat_sessions SET updated_at = :now WHERE id = :sid"),
                {"sid": session_id, "now": now_asst},
            )

    return QueryResponse(
        response=ai_response_text,
        metadata=resp_metadata,
        session_id=session_id,
    )
