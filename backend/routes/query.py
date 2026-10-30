import json
import logging
from typing import Any, Dict, List, Optional, Tuple
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import httpx
from sqlalchemy import Engine, text

from backend.database import (
    ensure_session_record,
    get_ai_service_url,
    get_db,
    parse_json_metadata,
    save_chat_message,
)
from backend.schemas import QueryRequest, QueryResponse
from shared.db import ensure_session_replica

logger = logging.getLogger("backend.routes.query")

router = APIRouter(tags=["query"])


def truncate_to_nearest_space(text_val: str, limit: int = 45) -> str:
    """Truncates text to the nearest whitespace before the character limit."""
    clean = text_val.strip()
    if len(clean) <= limit:
        return clean

    sliced = clean[:limit]
    last_space = sliced.rfind(" ")
    if last_space > 0:
        return f"{sliced[:last_space].rstrip()}..."
    return f"{sliced.rstrip()}..."


def _load_session_history(
    engine: Engine,
    session_id: str,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Loads ordered conversation history and active table metadata for a session."""
    history: List[Dict[str, Any]] = []
    active_metadata: Dict[str, Any] = {}

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT role, content, metadata
                FROM internal.chat_messages
                WHERE session_id = :sid
                ORDER BY id ASC
                """
            ),
            {"sid": session_id},
        ).fetchall()

    for row in rows:
        history.append({"role": row[0], "content": row[1]})
        meta_val = parse_json_metadata(row[2])
        if meta_val.get("table_names"):
            active_metadata["table_names"] = meta_val["table_names"]

    return history, active_metadata


def _prepare_query_context(request: QueryRequest) -> Dict[str, Any]:
    """Prepares session state, loads conversation history, and records the user turn."""
    effective_query = (request.query or "").strip()
    if not effective_query:
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    engine = get_db()
    session_id = request.session_id or str(uuid.uuid4())
    ensure_session_record(engine, session_id)
    ensure_session_replica(engine, session_id)

    history, active_metadata = _load_session_history(engine, session_id)
    active_metadata["session_id"] = session_id

    save_chat_message(engine, session_id, "user", effective_query)

    return {
        "engine": engine,
        "session_id": session_id,
        "effective_query": effective_query,
        "history": history,
        "active_metadata": active_metadata,
    }


def _build_response_metadata(
    raw_metadata: Optional[Dict[str, Any]],
    session_id: str,
    trace_id: Optional[str],
) -> Dict[str, Any]:
    """Enriches assistant response metadata with session and trace identifiers."""
    resp_metadata = dict(raw_metadata or {})
    resp_metadata["session_id"] = session_id
    if trace_id and not resp_metadata.get("trace_id"):
        resp_metadata["trace_id"] = trace_id
    return resp_metadata


def _save_assistant_response_and_update_title(
    engine: Engine,
    session_id: str,
    effective_query: str,
    ai_response_text: str,
    resp_metadata: Dict[str, Any],
) -> None:
    """Persists the assistant message and sets the session title on the first user turn."""
    now_asst = save_chat_message(engine, session_id, "assistant", ai_response_text, resp_metadata)

    with engine.begin() as conn:
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


@router.post("/api/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest) -> QueryResponse:
    """Processes natural language queries synchronously through the AI service."""
    ctx = _prepare_query_context(request)
    session_id = ctx["session_id"]
    effective_query = ctx["effective_query"]
    history = ctx["history"]
    active_metadata = ctx["active_metadata"]
    engine = ctx["engine"]
    ai_service_url = get_ai_service_url()

    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            ai_resp = await client.post(
                f"{ai_service_url}/process",
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
        logger.error(f"Failed to communicate with AI service at {ai_service_url}: {exc}")
        raise HTTPException(
            status_code=503,
            detail=f"AI service is unreachable at {ai_service_url}: {exc}",
        )

    ai_response_text = ai_data.get("response", "")
    ai_trace_id = ai_data.get("trace_id")
    resp_metadata = _build_response_metadata(ai_data.get("metadata"), session_id, ai_trace_id)

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
async def query_stream_endpoint(request: QueryRequest):
    """Streams real-time SSE status and result events from the AI service."""
    ctx = _prepare_query_context(request)
    session_id = ctx["session_id"]
    effective_query = ctx["effective_query"]
    history = ctx["history"]
    active_metadata = ctx["active_metadata"]
    engine = ctx["engine"]
    ai_service_url = get_ai_service_url()

    async def sse_stream():
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                async with client.stream(
                    "POST",
                    f"{ai_service_url}/process/stream",
                    json={
                        "query": effective_query,
                        "history": history,
                        "active_metadata": active_metadata,
                        "session_id": session_id,
                    },
                ) as response:
                    if response.status_code != 200:
                        err_text = await response.aread()
                        logger.error(
                            f"AI service stream returned error {response.status_code}: {err_text.decode('utf-8')}"
                        )
                        yield f"data: {json.dumps({'type': 'error', 'error': f'AI service error: {response.status_code}'})}\n\n"
                        return

                    buffer = ""
                    async for chunk in response.aiter_text():
                        buffer += chunk.replace("\r\n", "\n").replace("\r", "\n")
                        while "\n\n" in buffer:
                            idx = buffer.find("\n\n")
                            block = buffer[:idx]
                            buffer = buffer[idx + 2 :]

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
                                            resp_metadata = _build_response_metadata(
                                                event_data.get("metadata"),
                                                session_id,
                                                ai_trace_id,
                                            )

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
