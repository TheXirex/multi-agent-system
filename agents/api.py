import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    Initializes shared orchestrator agent on service startup.
    """
    global _orchestrator
    logger.info("Initializing Multi-Agent Orchestrator...")
    _orchestrator = build_orchestrator()

    try:
        from scripts.generate_data import seed_database
        engine = get_db()
        seed_database(engine, reset=False)
    except Exception as ex:
        logger.warning(f"Data seeding check skipped or failed: {ex}")

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


class QueryRequest(BaseModel):
    query: str = Field(..., description="Natural language query from user or UI")


class QueryResponse(BaseModel):
    user_query: str
    response: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    plan: Optional[Dict[str, Any]] = None
    raw_answer: Optional[Dict[str, Any]] = None


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """
    Health check endpoint for container orchestration.
    """
    return {"status": "ok", "service": "ai"}


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
    Runs Orchestrator agent to process natural language query and returns response with ID-only metadata.
    """
    global _orchestrator
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    if _orchestrator is None:
        _orchestrator = build_orchestrator()

    try:
        result: FinalOrchestratorResult = await _orchestrator.run(request.query)
        data = result.to_dict()
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

    if not rows and file_path and Path(file_path).is_file():
        try:
            df = pd.read_csv(file_path)
            rows = df.fillna("").to_dict(orient="records")
        except Exception:
            pass

    if rows and not columns_list:
        columns_list = list(rows[0].keys())

    columns = [{"name": c, "label": c, "field": c, "sortable": True, "align": "left"} for c in columns_list]

    return {
        "id": ds_id,
        "name": name,
        "file_name": file_name,
        "file_path": file_path,
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
