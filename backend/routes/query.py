import base64
from datetime import datetime
import json
import logging
from typing import Any, Dict, List, Optional
import uuid
import os
import httpx

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from agents.db_agent.tools import IngestTabularFileTool
from backend.database import get_db
from shared.db import ensure_session_replica
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


def _prepare_query_context(request: QueryRequest) -> Dict[str, Any]:
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

    ensure_session_replica(engine, session_id)

    # 2. Ingest any pending attachments and bind them specifically to this session
    attached_table_names: List[str] = []
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
                    t_name = ingest_res.get("table_name")
                    if t_name and t_name not in attached_table_names:
                        attached_table_names.append(t_name)
                    all_names = ingest_res.get("table_names", [])
                    for name in all_names:
                        if name not in attached_table_names:
                            attached_table_names.append(name)

                    attachment_summaries.append({
                        "filename": att.filename,
                        "table_name": t_name,
                        "table_names": all_names,
                    })
                    logger.info(f"Ingested attachment '{att.filename}' for session {session_id} -> tables={all_names}")
                elif ingest_res.get("status") == "clarification_needed":
                    return {
                        "early_clarification": QueryResponse(
                            response=ingest_res.get("response", ""),
                            session_id=session_id,
                            metadata=ingest_res.get("metadata", {}),
                        ),
                        "session_id": session_id,
                    }
            except Exception as e:
                logger.error(f"Error ingesting attachment {att.filename}: {e}")

    # Build effective query string
    if not raw_query and attachment_summaries:
        table_names_str = ", ".join(f"`{t}`" for t in attached_table_names)
        effective_query = f"I have uploaded data as table(s): {table_names_str}. Please provide an overview and summary of this data."
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
                for k in ("dataset_id", "dataset_ids", "table_names", "file_path"):
                    if k in meta_val and meta_val[k] is not None:
                        active_metadata[k] = meta_val[k]

    # Inject newly attached table names into active metadata and context
    active_metadata["session_id"] = session_id
    if attached_table_names:
        active_metadata["table_names"] = attached_table_names
        logger.info(f"Session {session_id} active metadata updated with tables: {attached_table_names}")

    # 4. Save User Message into PostgreSQL
    user_metadata: Dict[str, Any] = {}
    if request.attachments:
        user_metadata["attachments"] = [
            {"filename": a.filename, "tables": attached_table_names}
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

    return {
        "engine": engine,
        "session_id": session_id,
        "effective_query": effective_query,
        "history": history,
        "active_metadata": active_metadata,
        "attached_table_names": attached_table_names,
    }


def _save_assistant_response_and_update_title(
    engine,
    session_id: str,
    effective_query: str,
    ai_response_text: str,
    resp_metadata: Dict[str, Any],
) -> None:
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


@router.post("/api/query", response_model=QueryResponse)
@router.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest) -> QueryResponse:
    """
    Primary endpoint for natural language queries and attached dataset processing:
    Binds any attached files exclusively to the target session_id,
    maintains conversational memory and active session metadata in PostgreSQL,
    runs Orchestrator agent to process query, and persists message turns.
    """
    ctx = _prepare_query_context(request)
    if "early_clarification" in ctx:
        return ctx["early_clarification"]

    session_id = ctx["session_id"]
    effective_query = ctx["effective_query"]
    history = ctx["history"]
    active_metadata = ctx["active_metadata"]
    attached_table_names = ctx["attached_table_names"]
    engine = ctx["engine"]

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
    ai_trace_id = ai_data.get("trace_id")
    resp_metadata = dict(ai_data.get("metadata", {}))

    resp_metadata["session_id"] = session_id
    if ai_trace_id and not resp_metadata.get("trace_id"):
        resp_metadata["trace_id"] = ai_trace_id
    if attached_table_names and not resp_metadata.get("table_names"):
        resp_metadata["table_names"] = attached_table_names

    _save_assistant_response_and_update_title(
        engine=engine,
        session_id=session_id,
        effective_query=effective_query,
        ai_response_text=ai_response_text,
        resp_metadata=resp_metadata,
    )

    return QueryResponse(
        response=ai_response_text,
        metadata=resp_metadata,
        session_id=session_id,
        trace_id=ai_trace_id,
    )


@router.post("/api/query/stream")
@router.post("/query/stream")
async def query_stream_endpoint(request: QueryRequest):
    """
    Server-Sent Events (SSE) streaming endpoint for real-time progress updates.
    Yields 'status' events as tools execute and final 'result' event upon completion.
    """
    ctx = _prepare_query_context(request)
    if "early_clarification" in ctx:
        clarification_res = ctx["early_clarification"]

        async def early_gen():
            yield f"data: {json.dumps({'type': 'result', 'response': clarification_res.response, 'metadata': clarification_res.metadata, 'session_id': ctx['session_id']})}\n\n"

        return StreamingResponse(early_gen(), media_type="text/event-stream")

    session_id = ctx["session_id"]
    effective_query = ctx["effective_query"]
    history = ctx["history"]
    active_metadata = ctx["active_metadata"]
    attached_table_names = ctx["attached_table_names"]
    engine = ctx["engine"]

    async def sse_stream():
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                async with client.stream(
                    "POST",
                    f"{AI_SERVICE_URL}/process/stream",
                    json={
                        "query": effective_query,
                        "history": history,
                        "active_metadata": active_metadata,
                        "session_id": session_id,
                    },
                ) as response:
                    if response.status_code != 200:
                        err_text = await response.aread()
                        logger.error(f"AI service stream returned error {response.status_code}: {err_text.decode('utf-8')}")
                        yield f"data: {json.dumps({'type': 'error', 'error': f'AI service error: {response.status_code}'})}\n\n"
                        return

                    buffer = ""
                    async for chunk in response.aiter_text():
                        buffer += chunk.replace("\r\n", "\n").replace("\r", "\n")
                        while "\n\n" in buffer:
                            idx = buffer.find("\n\n")
                            block = buffer[:idx]
                            buffer = buffer[idx + 2:]

                            for raw_line in block.split("\n"):
                                line = raw_line.strip()
                                if line.startswith("data: "):
                                    payload_str = line[6:].strip()
                                    try:
                                        event_data = json.loads(payload_str)
                                        ev_type = event_data.get("type")

                                        if ev_type == "status":
                                            yield f"data: {json.dumps(event_data)}\n\n"

                                        elif ev_type == "result":
                                            ai_response_text = event_data.get("response", "")
                                            ai_trace_id = event_data.get("trace_id")
                                            resp_metadata = dict(event_data.get("metadata", {}))
                                            resp_metadata["session_id"] = session_id
                                            if ai_trace_id and not resp_metadata.get("trace_id"):
                                                resp_metadata["trace_id"] = ai_trace_id
                                            if attached_table_names and not resp_metadata.get("table_names"):
                                                resp_metadata["table_names"] = attached_table_names

                                            _save_assistant_response_and_update_title(
                                                engine=engine,
                                                session_id=session_id,
                                                effective_query=effective_query,
                                                ai_response_text=ai_response_text,
                                                resp_metadata=resp_metadata,
                                            )

                                            final_payload = {
                                                "type": "result",
                                                "response": ai_response_text,
                                                "metadata": resp_metadata,
                                                "session_id": session_id,
                                                "trace_id": ai_trace_id,
                                            }
                                            yield f"data: {json.dumps(final_payload)}\n\n"

                                        elif ev_type == "error":
                                            yield f"data: {json.dumps(event_data)}\n\n"

                                    except Exception as parse_ex:
                                        logger.warning(f"Error parsing SSE event in backend: {parse_ex}")

        except Exception as exc:
            logger.error(f"Streaming query error in backend: {exc}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"

    return StreamingResponse(sse_stream(), media_type="text/event-stream")
