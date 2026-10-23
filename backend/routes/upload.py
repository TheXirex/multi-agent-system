from datetime import datetime
import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy import text

from agents.db_agent.tools import IngestTabularFileTool
from backend.database import get_db
from shared.db import ensure_session_replica

logger = logging.getLogger("backend.routes.upload")

router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.post("")
@router.post("/")
async def upload_file(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
) -> Dict[str, Any]:
    """
    Uploads and ingests a CSV or Excel file by delegating directly to DBAgent's IngestTabularFileTool.
    Multi-sheet Excel files are partitioned into individual datasets in PostgreSQL.
    """
    filename = file.filename or "uploaded_data.csv"
    try:
        content = await file.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read uploaded file: {exc}")

    engine = get_db()
    if session_id:
        ensure_session_replica(engine, session_id)
    ingest_tool = IngestTabularFileTool(engine=engine)
    result = ingest_tool.execute(file_bytes=content, filename=filename, session_id=session_id)

    if result.get("status") == "error":
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Unknown file ingestion error"),
        )

    if result.get("status") == "clarification_needed":
        clarification_msg = result.get("response", "")
        if session_id:
            now = datetime.now()
            with engine.begin() as conn:
                conn.execute(
                    text("""
                        INSERT INTO internal.chat_messages (session_id, role, content, metadata, created_at)
                        VALUES (:sid, 'assistant', :content, :meta, :now)
                    """),
                    {
                        "sid": session_id,
                        "content": clarification_msg,
                        "meta": json.dumps(result.get("metadata", {})),
                        "now": now,
                    },
                )
        return {
            "status": "clarification_needed",
            "session_id": session_id,
            "message": clarification_msg,
            "questions": result.get("questions", []),
            "metadata": result.get("metadata", {}),
        }

    table_name = result.get("table_name")
    table_names = result.get("table_names", [table_name] if table_name else [])
    created_tables = result.get("tables", [])
    msg_markdown = result.get("response") or result.get("summary", "")

    if session_id:
        now = datetime.now()
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO internal.chat_messages (session_id, role, content, metadata, created_at)
                    VALUES (:sid, 'assistant', :content, :meta, :now)
                """),
                {
                    "sid": session_id,
                    "content": msg_markdown,
                    "meta": json.dumps({
                        "table_names": table_names,
                        "uploaded_file": filename,
                    }),
                    "now": now,
                },
            )
            conn.execute(
                text("UPDATE internal.chat_sessions SET updated_at = :now WHERE id = :sid"),
                {"sid": session_id, "now": now},
            )

    return {
        "status": "success",
        "session_id": session_id,
        "table_names": table_names,
        "tables": created_tables,
        "message": msg_markdown,
    }
