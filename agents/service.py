"""
Standalone AI Multi-Agent Service.
Exposes Orchestrator Agent, MCP tools, and LLM processing over HTTP.
"""
from contextlib import asynccontextmanager
import logging
import os
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from agents.orchestrator import FinalOrchestratorResult, OrchestratorAgent, build_orchestrator

logger = logging.getLogger("agents.service")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logging.getLogger("google_genai.models").setLevel(logging.WARNING)

_orchestrator: Optional[OrchestratorAgent] = None


def get_orchestrator() -> OrchestratorAgent:
    """
    Returns or lazily builds the shared OrchestratorAgent instance.
    """
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = build_orchestrator()
    return _orchestrator


class ProcessQueryRequest(BaseModel):
    query: str
    history: List[Dict[str, Any]] = Field(default_factory=list)
    active_metadata: Dict[str, Any] = Field(default_factory=dict)
    session_id: Optional[str] = None


class ProcessQueryResponse(BaseModel):
    response: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    session_id: Optional[str] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI Multi-Agent Service...")
    get_orchestrator()
    yield
    logger.info("Shutting down AI Multi-Agent Service.")


app = FastAPI(
    title="AI Multi-Agent Service",
    description="Dedicated microservice hosting the AI Orchestrator and MCP domain agents.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check() -> Dict[str, str]:
    return {"status": "ok", "service": "ai"}


@app.get("/tools")
async def list_tools() -> Dict[str, Any]:
    """
    Lists all MCP tools exposed by connected domain agents.
    """
    orchestrator = get_orchestrator()
    async with orchestrator.mcp_manager.open_session() as session:
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


@app.post("/process", response_model=ProcessQueryResponse)
async def process_query(req: ProcessQueryRequest) -> ProcessQueryResponse:
    """
    Executes natural language query through multi-agent orchestrator.
    """
    orchestrator = get_orchestrator()
    try:
        result: FinalOrchestratorResult = await orchestrator.process_query(
            query=req.query,
            history=req.history,
            active_metadata=req.active_metadata,
            session_id=req.session_id,
        )
        return ProcessQueryResponse(
            response=result.final_response,
            metadata=result.metadata,
            session_id=req.session_id,
        )
    except Exception as exc:
        logger.error(f"Error processing query in AI service: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


def main() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8001"))
    uvicorn.run("agents.service:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
