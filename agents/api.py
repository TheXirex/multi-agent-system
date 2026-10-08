import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agents.orchestrator.agent import OrchestratorAgent
from agents.orchestrator.factory import build_orchestrator
from agents.orchestrator.models import FinalOrchestratorResult

logger = logging.getLogger("ai_service")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

_orchestrator: Optional[OrchestratorAgent] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Initializes shared orchestrator agent on service startup.
    """
    global _orchestrator
    logger.info("Initializing Multi-Agent Orchestrator...")
    _orchestrator = build_orchestrator()
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
    Runs Planner -> Executor (via MCP) -> Finalizer and returns response with metadata.
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


def main() -> None:
    """
    Runs the AI FastAPI service using uvicorn.
    """
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("agents.api:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
