import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from backend.database import get_db
from shared.db import apply_session_search_path, get_session_schema_or_public

logger = logging.getLogger("backend.routes.artifacts")

router = APIRouter(tags=["artifacts"])


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint for backend container orchestration."""
    return {"status": "ok", "service": "backend"}


@router.get("/api/tables/{table_name}")
async def get_table_data(
    table_name: str,
    session_id: Optional[str] = None,
    limit: int = 200,
) -> Dict[str, Any]:
    """Retrieves column metadata and rows from a relational SQL table in the session or public schema."""
    engine = get_db()
    target_schema = get_session_schema_or_public(session_id)
    safe_table = "".join(c for c in table_name if c.isalnum() or c == "_")
    if not safe_table:
        raise HTTPException(status_code=400, detail="Invalid table name")

    try:
        with engine.connect() as conn:
            apply_session_search_path(conn, session_id)
            col_rows = conn.execute(
                text(
                    """
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_schema = :s AND table_name = :t
                    ORDER BY ordinal_position ASC
                    """
                ),
                {"s": target_schema, "t": safe_table},
            ).fetchall()

            if not col_rows and target_schema != "public":
                col_rows = conn.execute(
                    text(
                        """
                        SELECT column_name, data_type
                        FROM information_schema.columns
                        WHERE table_schema = 'public' AND table_name = :t
                        ORDER BY ordinal_position ASC
                        """
                    ),
                    {"t": safe_table},
                ).fetchall()
                target_schema = "public"

            if not col_rows:
                raise HTTPException(status_code=404, detail=f"Table '{safe_table}' not found.")

            col_names = [r[0] for r in col_rows]
            columns = [
                {"name": name, "label": name, "type": dtype}
                for name, dtype in col_rows
            ]

            data_rows = conn.execute(
                text(f'SELECT * FROM "{target_schema}"."{safe_table}" LIMIT :limit'),
                {"limit": limit},
            ).fetchall()

            rows = [
                dict(zip(col_names, [str(v) if v is not None else "" for v in dr]))
                for dr in data_rows
            ]

            total_count = (
                conn.execute(
                    text(f'SELECT COUNT(*) FROM "{target_schema}"."{safe_table}"')
                ).scalar()
                or 0
            )

            return {
                "id": safe_table,
                "name": safe_table,
                "table_name": safe_table,
                "schema": target_schema,
                "row_count": total_count,
                "columns": columns,
                "rows": rows,
            }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to query table '{safe_table}': {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database query error: {exc}")


@router.get("/api/charts/{chart_id}")
async def get_chart(chart_id: int) -> Dict[str, Any]:
    """Retrieves a Plotly chart JSON specification by chart_id."""
    engine = get_db()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, title, chart_type, spec, dataset_id, created_at "
                "FROM internal.generated_charts WHERE id = :id"
            ),
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


@router.get("/api/scripts/{script_id}")
async def get_script(script_id: int) -> Dict[str, Any]:
    """Retrieves an executed Python script record by script_id."""
    engine = get_db()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, script, language, task_description, dataset_id, created_at "
                "FROM internal.generated_scripts WHERE id = :id"
            ),
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
