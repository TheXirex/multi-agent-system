from datetime import datetime
import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from sqlalchemy import text

from agents.db_agent.tools import IngestTabularFileTool
from backend.database import get_db

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
    ingest_tool = IngestTabularFileTool(engine=engine)
    result = ingest_tool.execute(file_bytes=content, filename=filename, session_id=session_id)

    if result.get("status") == "error":
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "Unknown file ingestion error"),
        )

    created_datasets = result.get("datasets", [])
    primary_id = result.get("primary_dataset_id")
    dataset_ids = result.get("dataset_ids", [])

    msg_lines = [
        f"📁 **File uploaded successfully:** `{filename}`\n",
    ]
    if len(created_datasets) == 1:
        ds = created_datasets[0]
        msg_lines.append(f"Created dataset **#{ds['id']} ({ds['name']})**: {ds['row_count']} rows, {len(ds['columns'])} columns.")
        msg_lines.append("\n**Columns:** " + ", ".join(f"`{c}`" for c in ds["columns"]))
    else:
        msg_lines.append(f"Detected and partitioned into **{len(created_datasets)} separate datasets** (by sheet):")
        for ds in created_datasets:
            msg_lines.append(f"- **Dataset #{ds['id']} (`{ds['name']}`)**: {ds['row_count']} rows, columns: " + ", ".join(f"`{c}`" for c in ds["columns"]))

    msg_lines.append("\nYou can now request ML modeling, regression/classification, clustering, or data visualizations for this dataset.")
    msg_markdown = "\n".join(msg_lines)

    if session_id:
        now = datetime.now()
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO chat_messages (session_id, role, content, metadata, created_at)
                    VALUES (:sid, 'assistant', :content, :meta, :now)
                """),
                {
                    "sid": session_id,
                    "content": msg_markdown,
                    "meta": json.dumps({
                        "dataset_id": primary_id,
                        "dataset_ids": dataset_ids,
                        "uploaded_file": filename,
                    }),
                    "now": now,
                },
            )
            conn.execute(
                text("UPDATE chat_sessions SET updated_at = :now WHERE id = :sid"),
                {"sid": session_id, "now": now},
            )

    return {
        "status": "success",
        "session_id": session_id,
        "primary_dataset_id": primary_id,
        "dataset_ids": dataset_ids,
        "datasets": created_datasets,
        "message": msg_markdown,
    }
