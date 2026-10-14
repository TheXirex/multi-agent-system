from datetime import datetime
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import Engine, text
import uvicorn

from agents.db_agent.config import get_settings as get_db_settings
from agents.db_agent.db import create_db_engine
from agents.orchestrator import FinalOrchestratorResult, OrchestratorAgent, build_orchestrator

logger = logging.getLogger("ai_service")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logging.getLogger("google_genai.models").setLevel(logging.WARNING)

_orchestrator: Optional[OrchestratorAgent] = None
_db_engine: Optional[Engine] = None


def get_db() -> Engine:
    """
    Returns cached database engine for metadata resolution queries.
    """
    global _db_engine
    if _db_engine is None:
        db_cfg = get_db_settings()
        _db_engine = create_db_engine(db_cfg.database_url)
    return _db_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Initializes shared orchestrator agent on service startup and ensures schema.
    """
    global _orchestrator
    logger.info("Initializing Multi-Agent Orchestrator...")
    _orchestrator = build_orchestrator()

    try:
        from scripts.generate_data import seed_database
        engine = get_db()
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    id VARCHAR(36) PRIMARY KEY,
                    title VARCHAR(255) NOT NULL DEFAULT 'New Session',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id SERIAL PRIMARY KEY,
                    session_id VARCHAR(36) REFERENCES chat_sessions(id) ON DELETE CASCADE,
                    role VARCHAR(20) NOT NULL,
                    content TEXT NOT NULL,
                    metadata JSONB NOT NULL DEFAULT '{}',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))
        seed_database(engine, reset=False)
    except Exception as ex:
        logger.warning(f"Data seeding check or schema init skipped/failed: {ex}")

    yield
    logger.info("Shutting down AI service.")



app = FastAPI(
    title="AI Multi-Agent Service",
    description="Central backend service hosting the Orchestrator and domain agents via MCP.",
    version="0.1.0",
    lifespan=lifespan,
)

# Enable CORS for frontend flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class CreateSessionRequest(BaseModel):
    title: Optional[str] = "New Session"


class UpdateSessionRequest(BaseModel):
    title: str


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


class QueryRequest(BaseModel):
    query: str = Field(..., description="Natural language query from user or UI")
    session_id: Optional[str] = Field(None, description="Optional chat session ID for multi-turn conversation memory")


class QueryResponse(BaseModel):
    user_query: str
    response: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    plan: Optional[Dict[str, Any]] = None
    raw_answer: Optional[Dict[str, Any]] = None
    session_id: Optional[str] = None


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """
    Health check endpoint for container orchestration.
    """
    return {"status": "ok", "service": "ai"}


@app.get("/api/sessions", response_model=List[SessionSummary])
async def list_sessions() -> List[SessionSummary]:
    """
    Returns list of all chat sessions ordered by updated_at DESC.
    """
    engine = get_db()
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT s.id, s.title, s.created_at, s.updated_at,
                   COUNT(m.id) as message_count,
                   (SELECT content FROM chat_messages WHERE session_id = s.id ORDER BY id DESC LIMIT 1) as last_msg
            FROM chat_sessions s
            LEFT JOIN chat_messages m ON s.id = m.session_id
            GROUP BY s.id, s.title, s.created_at, s.updated_at
            ORDER BY s.updated_at DESC
        """)).fetchall()

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


@app.post("/api/sessions", response_model=SessionSummary)
async def create_session(req: Optional[CreateSessionRequest] = None) -> SessionSummary:
    """
    Creates a new chat session.
    """
    engine = get_db()
    new_id = str(uuid.uuid4())
    title = (req.title if req and req.title else "New Session").strip() or "New Session"
    now = datetime.now()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO chat_sessions (id, title, created_at, updated_at) VALUES (:id, :title, :now, :now)"),
            {"id": new_id, "title": title, "now": now},
        )
    return SessionSummary(
        id=new_id,
        title=title,
        created_at=str(now),
        updated_at=str(now),
        message_count=0,
        last_message=None,
    )


@app.get("/api/sessions/{session_id}", response_model=SessionDetail)
async def get_session(session_id: str) -> SessionDetail:
    """
    Retrieves full details and message history of a chat session.
    """
    engine = get_db()
    with engine.connect() as conn:
        s_row = conn.execute(
            text("SELECT id, title, created_at, updated_at FROM chat_sessions WHERE id = :id"),
            {"id": session_id},
        ).fetchone()

        if not s_row:
            raise HTTPException(status_code=404, detail="Session not found")

        m_rows = conn.execute(
            text("SELECT id, session_id, role, content, metadata, created_at FROM chat_messages WHERE session_id = :id ORDER BY id ASC"),
            {"id": session_id},
        ).fetchall()

    messages: List[ChatMessageItem] = []
    for mr in m_rows:
        meta_val = mr[4]
        if isinstance(meta_val, str):
            try:
                meta_val = json.loads(meta_val)
            except Exception:
                meta_val = {}
        elif not isinstance(meta_val, dict):
            meta_val = {}

        messages.append(
            ChatMessageItem(
                id=mr[0],
                session_id=str(mr[1]),
                role=str(mr[2]),
                content=str(mr[3]),
                metadata=meta_val,
                created_at=str(mr[5]),
            )
        )

    return SessionDetail(
        id=str(s_row[0]),
        title=str(s_row[1]),
        created_at=str(s_row[2]),
        updated_at=str(s_row[3]),
        messages=messages,
    )


@app.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str) -> Dict[str, Any]:
    """
    Deletes a session and its associated chat messages.
    """
    engine = get_db()
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM chat_sessions WHERE id = :id"),
            {"id": session_id},
        )
    return {"status": "deleted", "session_id": session_id}


@app.patch("/api/sessions/{session_id}")
async def update_session_title(session_id: str, req: UpdateSessionRequest) -> Dict[str, Any]:
    """
    Renames a chat session title.
    """
    engine = get_db()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE chat_sessions SET title = :title, updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
            {"id": session_id, "title": req.title.strip()},
        )
    return {"status": "updated", "session_id": session_id, "title": req.title.strip()}


@app.get("/api/tools")
async def list_tools() -> Dict[str, Any]:
    """
    Lists all tools exposed by connected MCP domain agents.
    """
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = build_orchestrator()

    async with _orchestrator.mcp_manager.open_session() as session:
        tools = await session.list_tools()
        return {
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "server": t.server_name,
                    "input_schema": t.input_schema,
                }
                for t in tools
            ]
        }


@app.post("/api/query", response_model=QueryResponse)
@app.post("/query", response_model=QueryResponse)
async def query_endpoint(request: QueryRequest) -> QueryResponse:
    """
    Primary endpoint for natural language queries:
    Maintains conversational memory (last 3 messages) and active session metadata in PostgreSQL,
    runs Orchestrator agent to process query, and persists message turns.
    """
    global _orchestrator
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    if _orchestrator is None:
        _orchestrator = build_orchestrator()

    engine = get_db()
    session_id = request.session_id

    # Ensure session exists or create a new one
    with engine.begin() as conn:
        if session_id:
            exists = conn.execute(
                text("SELECT 1 FROM chat_sessions WHERE id = :id"),
                {"id": session_id},
            ).scalar()
            if not exists:
                conn.execute(
                    text("INSERT INTO chat_sessions (id, title) VALUES (:id, 'New Session')"),
                    {"id": session_id},
                )
        else:
            session_id = str(uuid.uuid4())
            conn.execute(
                text("INSERT INTO chat_sessions (id, title) VALUES (:id, 'New Session')"),
                {"id": session_id},
            )

    # Fetch last 3 messages for conversational memory
    with engine.connect() as conn:
        recent_rows = conn.execute(
            text("""
                SELECT role, content, metadata
                FROM chat_messages
                WHERE session_id = :sid
                ORDER BY id DESC
                LIMIT 3
            """),
            {"sid": session_id},
        ).fetchall()

        # Fetch assistant messages to extract accumulated active metadata
        past_meta_rows = conn.execute(
            text("""
                SELECT metadata
                FROM chat_messages
                WHERE session_id = :sid AND role = 'assistant'
                ORDER BY id ASC
            """),
            {"sid": session_id},
        ).fetchall()

    # Chronological history (last 3 messages)
    conversation_history = [
        {"role": str(r[0]), "content": str(r[1])}
        for r in reversed(recent_rows)
    ]

    # Accumulate active metadata (e.g. latest dataset_id, chart_id, script_id)
    active_metadata: Dict[str, Any] = {}
    for r in past_meta_rows:
        m = r[0]
        if isinstance(m, str):
            try:
                m = json.loads(m)
            except Exception:
                m = {}
        if isinstance(m, dict):
            for k, v in m.items():
                if v:
                    active_metadata[k] = v

    try:
        result: FinalOrchestratorResult = await _orchestrator.run(
            user_query=request.query,
            conversation_history=conversation_history,
            active_metadata=active_metadata,
        )
        data = result.to_dict()

        final_resp_text = result.final_response or ""
        resp_metadata = result.metadata or (result.raw_answer.metadata if result.raw_answer else {})

        # Persist message turns in database
        now = datetime.now()
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO chat_messages (session_id, role, content, metadata, created_at) VALUES (:sid, 'user', :content, '{}', :now)"),
                {"sid": session_id, "content": request.query, "now": now},
            )
            conn.execute(
                text("INSERT INTO chat_messages (session_id, role, content, metadata, created_at) VALUES (:sid, 'assistant', :content, :meta, :now)"),
                {"sid": session_id, "content": final_resp_text, "meta": json.dumps(resp_metadata), "now": now},
            )

            # Update updated_at and auto-generate title if still default
            curr_title = conn.execute(
                text("SELECT title FROM chat_sessions WHERE id = :sid"),
                {"sid": session_id},
            ).scalar()
            if curr_title in ("New Session", "New Chat", None, ""):
                clean_title = request.query.strip().split("\n")[0][:45]
                conn.execute(
                    text("UPDATE chat_sessions SET title = :title, updated_at = :now WHERE id = :sid"),
                    {"sid": session_id, "title": clean_title, "now": now},
                )
            else:
                conn.execute(
                    text("UPDATE chat_sessions SET updated_at = :now WHERE id = :sid"),
                    {"sid": session_id, "now": now},
                )

        data["session_id"] = session_id
        return QueryResponse(**data)
    except Exception as exc:
        logger.error(f"Error processing query in AI service: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/datasets/{dataset_id}")
async def get_dataset(dataset_id: int) -> Dict[str, Any]:
    """
    Retrieves dataset metadata and rows by dataset_id.
    """
    engine = get_db()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, name, file_name, file_path, query, row_count, columns, data, created_at FROM generated_datasets WHERE id = :id"),
            {"id": dataset_id},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Dataset with ID {dataset_id} not found.")

    ds_id = row[0]
    name = row[1] or "dataset"
    file_name = row[2] or f"{name}.csv"
    file_path = row[3] or ""
    query = row[4] or ""
    row_count = row[5] or 0
    columns_list = row[6] or []
    data_val = row[7]
    created_at = str(row[8])

    rows: List[Dict[str, Any]] = []
    if data_val:
        if isinstance(data_val, str):
            try:
                rows = json.loads(data_val)
            except Exception:
                rows = []
        elif isinstance(data_val, list):
            rows = data_val

    if rows and not columns_list:
        columns_list = list(rows[0].keys())

    columns = [{"name": c, "label": c, "field": c, "sortable": True, "align": "left"} for c in columns_list]

    return {
        "id": ds_id,
        "name": name,
        "query": query,
        "row_count": len(rows) if rows else row_count,
        "columns": columns,
        "rows": rows,
        "created_at": created_at,
    }



@app.get("/api/charts/{chart_id}")
async def get_chart(chart_id: int) -> Dict[str, Any]:
    """
    Retrieves Plotly chart JSON specification by chart_id.
    """
    engine = get_db()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, title, chart_type, spec, dataset_id, created_at FROM generated_charts WHERE id = :id"),
            {"id": chart_id},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Chart with ID {chart_id} not found.")

    spec_data = row[3]
    if isinstance(spec_data, str):
        try:
            spec_data = json.loads(spec_data)
        except Exception:
            pass

    return {
        "id": row[0],
        "title": row[1],
        "chart_type": row[2],
        "spec": spec_data,
        "dataset_id": row[4],
        "created_at": str(row[5]),
    }


@app.get("/api/scripts/{script_id}")
async def get_script(script_id: int) -> Dict[str, Any]:
    """
    Retrieves executed script content by script_id.
    """
    engine = get_db()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, script, language, task_description, dataset_id, created_at FROM generated_scripts WHERE id = :id"),
            {"id": script_id},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Script with ID {script_id} not found.")

    return {
        "id": row[0],
        "script": row[1],
        "language": row[2],
        "task_description": row[3],
        "dataset_id": row[4],
        "created_at": str(row[5]),
    }


def main() -> None:
    """
    Runs the AI FastAPI service using uvicorn.
    """
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("agents.api:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
