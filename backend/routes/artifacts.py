import json
import logging
from typing import Any, Dict, List

import os
import httpx
from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from backend.database import get_db

logger = logging.getLogger("backend.routes.artifacts")

router = APIRouter(tags=["artifacts"])

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://ai:8001").rstrip("/")


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """
    Health check endpoint for backend container orchestration.
    """
    return {"status": "ok", "service": "backend"}


@router.get("/api/tools")
async def list_tools() -> Dict[str, Any]:
    """
    Lists all tools exposed by connected MCP domain agents via the AI service.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{AI_SERVICE_URL}/tools")
            if resp.status_code == 200:
                return resp.json()
    except Exception as exc:
        logger.warning(f"Could not fetch tools from AI service at {AI_SERVICE_URL}: {exc}")
    return {"tools": []}


@router.get("/api/datasets/{dataset_id}")
async def get_dataset(dataset_id: int) -> Dict[str, Any]:
    """
    Retrieves dataset metadata and rows by dataset_id.
    """
    engine = get_db()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, name, file_name, file_path, query, row_count, columns, data, created_at FROM internal.user_datasets WHERE id = :id"),
            {"id": dataset_id},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail=f"Dataset with ID {dataset_id} not found.")

    ds_id = row[0]
    name = row[1] or "dataset"
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


@router.get("/api/charts/{chart_id}")
async def get_chart(chart_id: int) -> Dict[str, Any]:
    """
    Retrieves Plotly chart JSON specification by chart_id.
    """
    engine = get_db()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, title, chart_type, spec, dataset_id, created_at FROM internal.generated_charts WHERE id = :id"),
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

    if isinstance(spec_data, dict):
        layout = spec_data.get("layout")
        if isinstance(layout, dict):
            def _is_color_str(val: Any) -> bool:
                if not isinstance(val, str):
                    return False
                s = val.strip().lower()
                if s.startswith("<b>") and s.endswith("</b>"):
                    s = s[3:-4].strip()
                if s.startswith("<span>") and s.endswith("</span>"):
                    s = s[6:-7].strip()
                return s in ("color", "colour", "color:", "colour:")

            legend = layout.get("legend")
            if isinstance(legend, dict):
                lt = legend.get("title")
                if isinstance(lt, dict) and _is_color_str(lt.get("text")):
                    lt["text"] = ""
                elif _is_color_str(lt):
                    legend["title"] = ""

            if _is_color_str(layout.get("legend_title_text")):
                layout["legend_title_text"] = ""

            lt_top = layout.get("legend_title")
            if isinstance(lt_top, dict) and _is_color_str(lt_top.get("text")):
                lt_top["text"] = ""
            elif _is_color_str(lt_top):
                layout["legend_title"] = ""

    return {
        "id": row[0],
        "title": row[1],
        "chart_type": row[2],
        "spec": spec_data,
        "dataset_id": row[4],
        "created_at": str(row[5]),
    }


@router.get("/api/scripts/{script_id}")
async def get_script(script_id: int) -> Dict[str, Any]:
    """
    Retrieves executed script content by script_id.
    """
    engine = get_db()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, script, language, task_description, dataset_id, created_at FROM internal.generated_scripts WHERE id = :id"),
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
